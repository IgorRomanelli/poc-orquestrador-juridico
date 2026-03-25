"""
Cliente Serper.dev — busca reversa de imagem via Google Lens.

Recebe uma URL de imagem (presigned URL do S3) e retorna lista de
páginas onde a imagem aparece, no mesmo formato dos outros clientes.

Variável de ambiente: SERPER_API_KEY
"""

import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("SERPER_API_KEY", "")
_LENS_URL = "https://google.serper.dev/lens"


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


async def search_by_image_url(image_url: str) -> dict:
    """
    Busca páginas que contêm a imagem usando Serper Google Lens.

    Args:
        image_url: URL da imagem (presigned URL do S3, expira em 60s).

    Returns:
        dict com status, results e message (mesmo formato dos outros clientes).
    """
    if not _API_KEY:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": "SERPER_API_KEY não configurada — configure no .env",
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _LENS_URL,
                headers={"X-API-KEY": _API_KEY, "Content-Type": "application/json"},
                json={"url": image_url},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": f"Serper falhou: {exc}",
        }

    raw_results = data.get("organic", [])
    results = [
        {
            "page_url": item.get("link", ""),
            "domain": _extract_domain(item.get("link", "")),
            "source": "serper",
            "confidence": None,
            "source_confidence": 0.70,  # Google Lens encontrou a imagem na página
            "preview_thumbnail": item.get("thumbnailUrl", ""),
            "image_url": item.get("imageUrl", ""),
        }
        for item in raw_results
        if item.get("link")
    ]

    return {
        "results": results,
        "status": "found" if results else "not_found",
        "requires_manual_review": False,
        "message": None,
    }
