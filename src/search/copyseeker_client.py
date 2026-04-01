"""
Cliente CopySeeker — busca reversa de imagem via RapidAPI.

Recebe uma URL de imagem (presigned URL do S3) e retorna lista de
páginas onde a imagem aparece, no mesmo formato dos outros clientes de busca.

API: GET https://reverse-image-search-by-copyseeker.p.rapidapi.com/
     ?imageUrl=<url_da_imagem>
     Headers: x-rapidapi-key, x-rapidapi-host

Variável de ambiente: COPYSEEKER_API_KEY
"""

import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_API_KEY: str = os.getenv("COPYSEEKER_API_KEY", "")
_RAPIDAPI_HOST = "reverse-image-search-by-copyseeker.p.rapidapi.com"
_ENDPOINT = f"https://{_RAPIDAPI_HOST}/"


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


async def search_by_image_url(image_url: str) -> dict:
    """
    Busca páginas que contêm a imagem usando CopySeeker via RapidAPI.

    Args:
        image_url: URL pública da imagem (presigned URL do S3).

    Returns:
        dict com status, results e message — mesmo formato dos outros clientes.
    """
    if not _API_KEY:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": "COPYSEEKER_API_KEY não configurada — configure no .env",
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                _ENDPOINT,
                headers={
                    "x-rapidapi-key": _API_KEY,
                    "x-rapidapi-host": _RAPIDAPI_HOST,
                },
                params={"imageUrl": image_url},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": f"CopySeeker retornou HTTP {exc.response.status_code} — validar manualmente",
        }
    except Exception:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": "CopySeeker falhou com erro inesperado — validar manualmente",
        }

    pages = data.get("Pages", [])
    results = [
        {
            "page_url": page.get("Url", ""),
            "domain": _extract_domain(page.get("Url", "")),
            "source": "copyseeker",
            "confidence": None,
            "source_confidence": 0.70,
            "preview_thumbnail": (page.get("MatchingImages") or [""])[0],
            "image_url": "",
        }
        for page in pages
        if page.get("Url")
    ]

    return {
        "results": results,
        "status": "found" if results else "not_found",
        "requires_manual_review": False,
        "message": None,
    }
