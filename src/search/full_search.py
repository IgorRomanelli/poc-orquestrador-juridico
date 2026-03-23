"""
Orquestrador completo: combina as 4 fontes de busca em paralelo.

Fluxo:
    1. Upload da imagem para S3 → obtém presigned URL temporária (60s)
    2. asyncio.gather das 3 fontes em paralelo:
         - orchestrator.search_image (FaceCheck + Google Vision + Rekognition)
         - serper_client.search_by_image_url (Google Lens via Serper)
         - searchapi_client.search_by_image_url (Google Lens via SearchAPI)
    3. S3 cleanup no finally (sempre executado)
    4. Combina e deduplica por page_url (mantém maior confidence)
"""

import asyncio

from . import s3_temp_client, searchapi_client, serper_client
from .orchestrator import search_image


def _confidence_value(item: dict) -> float:
    """Retorna confidence como float comparável; None vira -1 (menor prioridade)."""
    c = item.get("confidence")
    return c if c is not None else -1.0


def _deduplicate(items: list[dict]) -> list[dict]:
    """Deduplica por page_url mantendo o item com maior confidence."""
    best: dict[str, dict] = {}
    for item in items:
        url = item.get("page_url", "")
        if not url:
            continue
        if url not in best or _confidence_value(item) > _confidence_value(best[url]):
            best[url] = item
    return list(best.values())


async def run_full_search(image_path: str, image_bytes: bytes) -> list[dict]:
    """
    Executa busca completa nas 4 fontes e retorna resultados deduplicados.

    Args:
        image_path: caminho local da imagem (usado pelo orchestrator).
        image_bytes: bytes da imagem (usado para upload S3 e clientes de URL).

    Returns:
        Lista de dicts deduplicados por page_url com chaves:
        image_url, page_url, source, confidence (e demais campos opcionais).

    Raises:
        RuntimeError: if the S3 upload fails (search cannot proceed without presigned URL).
        Exception: any exception from the search sources propagates after S3 cleanup.

    Note:
        If any search source raises, asyncio.gather propagates the first exception
        and all results are lost. Partial results are not supported (POC limitation).
    """
    try:
        presigned_url, s3_key = s3_temp_client.upload_and_get_url(image_bytes)
    except Exception as exc:
        raise RuntimeError(f"Failed to upload image to S3 for search: {exc}") from exc

    try:
        orchestrator_result, serper_result, searchapi_result = await asyncio.gather(
            search_image(image_path),
            serper_client.search_by_image_url(presigned_url),
            searchapi_client.search_by_image_url(presigned_url),
        )
    finally:
        s3_temp_client.delete_object(s3_key)

    all_items: list[dict] = []
    for result in (orchestrator_result, serper_result, searchapi_result):
        all_items.extend(result.get("results", []))

    return _deduplicate(all_items)
