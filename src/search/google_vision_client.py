"""
Cliente Google Cloud Vision API — Web Detection.

Usa REST direto via httpx com GOOGLE_CLOUD_API_KEY (sem SDK, sem service account).
Extrai páginas com imagens correspondentes e imagens visualmente similares.

Status possíveis: "found" | "not_found" | "error"
"""

import base64
import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY", "")
_TIMEOUT_SECONDS = 30.0
_MAX_RESULTS = int(os.getenv("GOOGLE_VISION_MAX_RESULTS", "20"))


# ─── helpers privados ──────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Extrai domínio de uma URL, removendo www."""
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")
    except Exception:
        return url


def _build_payload(image_b64: str) -> dict:
    return {
        "requests": [
            {
                "image": {"content": image_b64},
                "features": [{"type": "WEB_DETECTION", "maxResults": _MAX_RESULTS}],
            }
        ]
    }


def _normalize_response(web_detection: dict) -> list[dict]:
    """
    Converte resposta WebDetection para lista de itens normalizados.

    Prioridade:
        1. pagesWithMatchingImages — page_url + image_url de imagens na página
        2. visuallySimilarImages — imagem similar sem page_url
    """
    results = []
    seen_page_urls = set()

    for page in web_detection.get("pagesWithMatchingImages", []):
        page_url = page.get("url", "")
        if not page_url or page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)

        # Preferir full match, fallback para partial
        image_url = None
        full_matches = page.get("fullMatchingImages", [])
        partial_matches = page.get("partialMatchingImages", [])
        if full_matches:
            image_url = full_matches[0].get("url")
        elif partial_matches:
            image_url = partial_matches[0].get("url")

        # confidence = None → Rekognition fará a comparação facial real.
        # source_confidence = estimativa estrutural usada só se Rekognition não estiver disponível.
        source_confidence = 0.85 if full_matches else 0.65
        results.append({
            "image_url": image_url,
            "page_url": page_url,
            "domain": _extract_domain(page_url),
            "source": "google_vision",
            "confidence": None,
            "source_confidence": source_confidence,
            "preview_thumbnail": None,
        })

    for img in web_detection.get("visuallySimilarImages", []):
        image_url = img.get("url", "")
        if not image_url:
            continue
        results.append({
            "image_url": image_url,
            "page_url": image_url,   # sem page_url — usar image_url como referência
            "domain": _extract_domain(image_url),
            "source": "google_vision",
            "confidence": None,
            "source_confidence": 0.40,  # visualmente similar, sem correspondência confirmada
            "preview_thumbnail": None,
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
        "requires_manual_review": False,
        "message": "Google Vision não encontrou correspondências",
    }


# ─── função pública ────────────────────────────────────────────────────────────

async def search_by_image(image_path: str) -> dict:
    """
    Busca reversa de imagem via Google Cloud Vision Web Detection.

    Args:
        image_path: caminho local para o arquivo de imagem.

    Returns:
        dict com status explícito, results normalizados e requires_manual_review.
    """
    if not _API_KEY:
        return _error_result("GOOGLE_CLOUD_API_KEY não configurada")

    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        return _error_result(f"Arquivo não encontrado: {image_path}")
    except Exception as exc:
        return _error_result(f"Erro ao ler imagem: {exc}")

    url = f"{_VISION_URL}?key={_API_KEY}"
    payload = _build_payload(image_b64)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
    except httpx.TimeoutException:
        return _error_result("Google Vision timeout após 30s")
    except Exception as exc:
        return _error_result(f"Erro de conexão Google Vision: {exc}")

    if response.status_code == 400:
        return _error_result("Google Vision: request inválido (400) — verificar chave ou formato da imagem")
    if response.status_code == 403:
        return _error_result("Google Vision: acesso negado (403) — verificar GOOGLE_CLOUD_API_KEY e restrições da chave")
    if response.status_code == 429:
        return _error_result("Google Vision: rate limit atingido (429)")
    if response.status_code != 200:
        return _error_result(f"Google Vision HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception:
        return _error_result("Resposta inválida da Google Vision API")

    response_data = data.get("responses", [{}])[0]

    if response_data.get("error"):
        err = response_data["error"]
        return _error_result(f"Google Vision API error: {err.get('message', err)}")

    web_detection = response_data.get("webDetection", {})
    results = _normalize_response(web_detection)

    if not results:
        return _not_found_result()

    return {
        "results": results,
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }
