"""
Orquestrador de busca de imagem: coordena FaceCheck e Google Vision em paralelo.

Fluxo:
    asyncio.gather(
        search_by_face(image_path),    → FaceCheck (busca facial)
        search_by_image(image_path),   → Google Vision (busca reversa)
    )
    → aggregate(facecheck_result, vision_result)

Status global: "found" | "partial" | "not_found" | "error"
"""

import asyncio
import time

from .aggregator import aggregate
from .facecheck_client import search_by_face
from .google_vision_client import search_by_image


# ─── helpers privados ──────────────────────────────────────────────────────────

def _exception_to_error(exc: Exception, label: str) -> dict:
    return {
        "results": [],
        "status": "error",
        "requires_manual_review": True,
        "message": f"{label} falhou com erro inesperado: {exc}",
    }


# ─── função pública ────────────────────────────────────────────────────────────

async def search_image(image_path: str) -> dict:
    """
    Executa busca de imagem completa: FaceCheck + Google Vision em paralelo.

    Args:
        image_path: caminho local para o arquivo de imagem.

    Returns:
        dict com status global, results agregados, domains e search_time_seconds.
    """
    start = time.monotonic()

    facecheck_result, vision_result = await asyncio.gather(
        search_by_face(image_path),
        search_by_image(image_path),
        return_exceptions=True,
    )

    if isinstance(facecheck_result, Exception):
        facecheck_result = _exception_to_error(facecheck_result, "FaceCheck")
    if isinstance(vision_result, Exception):
        vision_result = _exception_to_error(vision_result, "GoogleVision")

    result = aggregate(facecheck_result, vision_result)
    result["search_time_seconds"] = round(time.monotonic() - start, 2)

    return result
