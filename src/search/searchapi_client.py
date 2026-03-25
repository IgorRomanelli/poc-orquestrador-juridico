"""
Cliente SearchAPI — busca reversa de imagem via Google Lens.

Recebe uma URL de imagem (presigned URL do S3) e retorna lista de
páginas onde a imagem aparece, no mesmo formato dos outros clientes.

Variável de ambiente: SEARCHAPI_KEY
"""

import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("SEARCHAPI_KEY", "")
_SEARCH_URL = "https://www.searchapi.io/api/v1/search"


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


async def search_by_image_url(image_url: str) -> dict:
    """
    Busca páginas que contêm a imagem usando SearchAPI Google Lens.

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
            "message": "SEARCHAPI_KEY não configurada — configure no .env",
        }

    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": _API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": f"SearchAPI falhou: {exc}",
        }

    raw_results = data.get("visual_matches", [])
    results = [
        {
            "page_url": item.get("link", ""),
            "domain": _extract_domain(item.get("link", "")),
            "source": "searchapi",
            "confidence": 0.70,  # Google Lens encontrou a imagem na página
            "preview_thumbnail": item.get("thumbnail", ""),
            "image_url": item.get("image", {}).get("link", ""),
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
