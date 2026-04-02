"""
Cliente SearchAPI — busca reversa de imagem via Google Lens (exact + visual).

Usa search_type=all para obter exact_matches (imagem idêntica, score 0.85)
e visual_matches (imagem parecida, score 0.70) em uma única chamada.

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
    Busca páginas que contêm a imagem usando SearchAPI Google Lens (search_type=all).

    Retorna exact_matches (score 0.85) e visual_matches (score 0.70) numa
    única chamada à API. A deduplicação por page_url em full_search mantém
    o item de maior confidence quando há sobreposição.

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
        "search_type": "all",
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

    results = []

    for item in data.get("exact_matches", []):
        if item.get("link"):
            results.append({
                "page_url": item.get("link", ""),
                "domain": _extract_domain(item.get("link", "")),
                "source": "searchapi",
                "confidence": None,
                "source_confidence": 0.85,  # imagem idêntica ou quase
                "preview_thumbnail": item.get("thumbnail", ""),
                "image_url": item.get("image", {}).get("link", ""),
            })

    for item in data.get("visual_matches", []):
        if item.get("link"):
            results.append({
                "page_url": item.get("link", ""),
                "domain": _extract_domain(item.get("link", "")),
                "source": "searchapi",
                "confidence": None,
                "source_confidence": 0.70,  # imagem visualmente parecida
                "preview_thumbnail": item.get("thumbnail", ""),
                "image_url": item.get("image", {}).get("link", ""),
            })

    return {
        "results": results,
        "status": "found" if results else "not_found",
        "requires_manual_review": False,
        "message": None,
    }
