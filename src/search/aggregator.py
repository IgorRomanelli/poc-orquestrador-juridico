"""
Agregador de resultados de busca de imagem.

Recebe os resultados brutos de FaceCheck e Google Vision e produz
uma lista unificada, deduplicada e ordenada por relevância.

Regra de deduplicação: por page_url exato.
Quando o mesmo domínio aparece nas duas APIs com page_urls distintos, ambos são mantidos.
"""

import asyncio
import base64

import httpx

from urllib.parse import urlparse

from .rekognition_client import compare_faces

_DOWNLOAD_TIMEOUT = 5.0


# ─── helpers privados ──────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")
    except Exception:
        return url


def _confidence_key(item: dict):
    """Chave de ordenação: confidence desc, None vai para o final."""
    c = item.get("confidence")
    return (0, -c) if c is not None else (1, 0)


def _compute_status(facecheck: dict, vision: dict) -> tuple[str, bool]:
    """
    Computa status global e requires_manual_review.

    found    → pelo menos uma fonte encontrou resultados
    not_found → nenhuma fonte encontrou
    error    → pelo menos uma com erro E nenhuma com found
    partial  → uma found, outra error
    """
    fc_status = facecheck.get("status")
    gv_status = vision.get("status")

    any_found = fc_status == "found" or gv_status == "found"
    any_error = fc_status == "error" or gv_status == "error"

    if any_found and any_error:
        status = "partial"
    elif any_found:
        status = "found"
    elif any_error:
        status = "error"
    else:
        status = "not_found"

    requires_manual = any(
        r.get("requires_manual_review")
        for r in (facecheck, vision)
    )

    return status, requires_manual


def _collect_messages(facecheck: dict, vision: dict) -> str | None:
    messages = []
    for r in (facecheck, vision):
        msg = r.get("message")
        if msg:
            messages.append(msg)
    return " | ".join(messages) if messages else None


# ─── função pública ────────────────────────────────────────────────────────────

def aggregate(facecheck_result: dict, vision_result: dict) -> dict:
    """
    Agrega, deduplica e ordena resultados de FaceCheck + Google Vision.

    Args:
        facecheck_result: dict retornado por search_by_face()
        vision_result: dict retornado por search_by_image()

    Returns:
        dict consolidado com results, domains, contagens e status global.
    """
    all_items = []
    all_items.extend(facecheck_result.get("results", []))
    all_items.extend(vision_result.get("results", []))

    total_raw = len(all_items)

    # Deduplicar por page_url (primeira ocorrência vence)
    seen_page_urls: set[str] = set()
    deduplicated = []
    for item in all_items:
        page_url = item.get("page_url", "")
        if page_url and page_url not in seen_page_urls:
            seen_page_urls.add(page_url)
            deduplicated.append(item)

    # Ordenar por confidence desc (None vai para o final)
    deduplicated.sort(key=_confidence_key)

    # Extrair domínios únicos preservando ordem de aparição
    domains: list[str] = []
    seen_domains: set[str] = set()
    for item in deduplicated:
        d = item.get("domain", "")
        if d and d not in seen_domains:
            seen_domains.add(d)
            domains.append(d)

    status, requires_manual = _compute_status(facecheck_result, vision_result)
    message = _collect_messages(facecheck_result, vision_result)

    return {
        "results": deduplicated,
        "domains": domains,
        "total_raw": total_raw,
        "total_deduplicated": len(deduplicated),
        "status": status,
        "requires_manual_review": requires_manual,
        "message": message,
    }


# ─── enriquecimento Rekognition ────────────────────────────────────────────────


def _to_jpeg(raw_bytes: bytes) -> bytes:
    """Converte bytes de imagem para JPEG (Rekognition exige JPEG ou PNG)."""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _get_target_bytes(item: dict) -> bytes | None:
    """Obtém bytes da imagem-alvo em JPEG: base64 thumbnail ou download via image_url."""
    thumbnail = item.get("preview_thumbnail") or ""
    if thumbnail.startswith("data:") and ";base64," in thumbnail:
        try:
            b64_part = thumbnail.split(";base64,", 1)[1]
            raw = base64.b64decode(b64_part)
            return _to_jpeg(raw)
        except Exception:
            return None

    image_url = item.get("image_url")
    if image_url:
        try:
            response = httpx.get(image_url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
            if response.status_code == 200:
                return _to_jpeg(response.content)
        except Exception:
            pass

    return None


async def enrich_with_rekognition(items: list[dict], source_image_bytes: bytes) -> list[dict]:
    """
    Enriquece cada item com confidence_rekognition via Amazon Rekognition CompareFaces.

    Args:
        items: lista de resultados agregados.
        source_image_bytes: bytes da foto original do cliente.

    Returns:
        A mesma lista com confidence_rekognition adicionado onde possível.
        Itens sem imagem acessível ou com erro ficam com confidence_rekognition=None.
    """
    async def _enrich_one(item: dict) -> None:
        target_bytes = await asyncio.to_thread(_get_target_bytes, item)
        if target_bytes is None:
            item["confidence_rekognition"] = None
            return
        result = await asyncio.to_thread(compare_faces, source_image_bytes, target_bytes)
        item["confidence_rekognition"] = result.get("similarity")

    await asyncio.gather(*(_enrich_one(item) for item in items))
    return items
