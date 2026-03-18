"""
Cliente FaceCheck.ID — busca facial por imagem.

Fluxo (2 etapas obrigatórias):
    1. POST /api/upload_pic  → obtém id_search
    2. POST /api/search      → polling até output != None ou timeout

Status possíveis: "found" | "not_found" | "error"

FACECHECK_DEMO=true por padrão — não deduz créditos, resultados menos precisos.
Modo produção: FACECHECK_DEMO=false no .env.
"""

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_FACECHECK_BASE = "https://facecheck.id"
_UPLOAD_URL = _FACECHECK_BASE + "/api/upload_pic"
_SEARCH_URL = _FACECHECK_BASE + "/api/search"
_API_TOKEN = os.getenv("FACECHECK_API_KEY", "")
_DEMO_MODE = os.getenv("FACECHECK_DEMO", "true").lower() == "true"
_POLLING_INTERVAL = 1.0     # segundos entre polls
_MAX_POLLING_SECONDS = 120  # timeout total de polling
_UPLOAD_TIMEOUT = 30.0
_SEARCH_TIMEOUT = 15.0


# ─── helpers privados ──────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Extrai domínio de uma URL, removendo www."""
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")
    except Exception:
        return url


def _normalize_items(raw_items: list) -> list[dict]:
    """Converte items brutos do FaceCheck para estrutura padrão."""
    results = []
    for item in raw_items:
        page_url = item.get("url", "")
        results.append({
            "image_url": None,           # FaceCheck não retorna URL direta da imagem
            "page_url": page_url,
            "domain": _extract_domain(page_url),
            "source": "facecheck",
            "confidence": round(item.get("score", 0) / 100, 4) if item.get("score") is not None else None,
            "preview_thumbnail": item.get("base64"),
        })
    return results


def _error_result(message: str) -> dict:
    return {
        "results": [],
        "status": "error",
        "requires_manual_review": True,
        "message": message,
    }


def _not_found_result() -> dict:
    return {
        "results": [],
        "status": "not_found",
        "requires_manual_review": True,
        "message": "FaceCheck não encontrou correspondências",
    }


# ─── clientes internos ────────────────────────────────────────────────────────

async def _upload(client: httpx.AsyncClient, image_path: str) -> tuple[str | None, str | None]:
    """Faz upload da imagem. Retorna (id_search, error_message)."""
    headers = {"accept": "application/json", "Authorization": _API_TOKEN}

    try:
        with open(image_path, "rb") as f:
            files = {"images": f, "id_search": (None, "")}
            response = await client.post(_UPLOAD_URL, headers=headers, files=files, timeout=_UPLOAD_TIMEOUT)
    except httpx.TimeoutException:
        return None, "FaceCheck upload timeout após 30s"
    except FileNotFoundError:
        return None, f"Arquivo não encontrado: {image_path}"
    except Exception as exc:
        return None, f"Erro de conexão no upload FaceCheck: {exc}"

    try:
        data = response.json()
    except Exception:
        return None, f"Resposta inválida do upload FaceCheck (HTTP {response.status_code})"

    if data.get("error"):
        return None, f"FaceCheck upload error: {data['error']} ({data.get('code', '')})"

    return data.get("id_search"), None


async def _poll(client: httpx.AsyncClient, id_search: str) -> tuple[list | None, str | None]:
    """Polling até output estar disponível ou timeout. Retorna (items, error_message)."""
    headers = {"accept": "application/json", "Authorization": _API_TOKEN}
    json_data = {
        "id_search": id_search,
        "with_progress": True,
        "status_only": False,
        "demo": _DEMO_MODE,
    }

    deadline = time.monotonic() + _MAX_POLLING_SECONDS

    while time.monotonic() < deadline:
        try:
            response = await client.post(_SEARCH_URL, headers=headers, json=json_data, timeout=_SEARCH_TIMEOUT)
        except httpx.TimeoutException:
            return None, "FaceCheck search timeout"
        except Exception as exc:
            return None, f"Erro de conexão no search FaceCheck: {exc}"

        try:
            data = response.json()
        except Exception:
            return None, "Resposta inválida do search FaceCheck"

        if data.get("error"):
            return None, f"FaceCheck search error: {data['error']} ({data.get('code', '')})"

        if data.get("output"):
            return data["output"].get("items", []), None

        await asyncio.sleep(_POLLING_INTERVAL)

    return None, f"FaceCheck timeout após {_MAX_POLLING_SECONDS}s de polling"


# ─── função pública ────────────────────────────────────────────────────────────

async def search_by_face(image_path: str) -> dict:
    """
    Busca facial via FaceCheck.ID.

    Args:
        image_path: caminho local para o arquivo de imagem.

    Returns:
        dict com status explícito, results normalizados e requires_manual_review.
    """
    if not _API_TOKEN:
        return _error_result("FACECHECK_API_KEY não configurada")

    async with httpx.AsyncClient() as client:
        id_search, upload_error = await _upload(client, image_path)
        if upload_error:
            return _error_result(upload_error)

        items, poll_error = await _poll(client, id_search)
        if poll_error:
            return _error_result(poll_error)

    if not items:
        return _not_found_result()

    results = _normalize_items(items)
    return {
        "results": results,
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }
