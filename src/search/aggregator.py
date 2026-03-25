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


def _compute_status(*sources: dict) -> tuple[str, bool]:
    """
    Computa status global e requires_manual_review para N fontes.

    found    → pelo menos uma fonte encontrou resultados
    not_found → nenhuma fonte encontrou
    error    → pelo menos uma com erro E nenhuma com found
    partial  → pelo menos uma found e pelo menos uma error
    """
    any_found = any(s.get("status") == "found" for s in sources)
    any_error = any(s.get("status") == "error" for s in sources)

    if any_found and any_error:
        status = "partial"
    elif any_found:
        status = "found"
    elif any_error:
        status = "error"
    else:
        status = "not_found"

    requires_manual = any(s.get("requires_manual_review") for s in sources)
    return status, requires_manual


def _collect_messages(*sources: dict) -> str | None:
    messages = [s.get("message") for s in sources if s.get("message")]
    return " | ".join(messages) if messages else None


# ─── função pública ────────────────────────────────────────────────────────────

def aggregate(*source_results: dict) -> dict:
    """
    Agrega, deduplica e ordena resultados de múltiplas fontes de busca.

    Args:
        *source_results: dicts retornados por qualquer cliente de busca.
                         Primeiro argumento = FaceCheck, segundo = Google Vision.

    Returns:
        dict consolidado com results, domains, contagens e status global.
    """
    all_items = []
    for r in source_results:
        all_items.extend(r.get("results", []))

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

    status, requires_manual = _compute_status(*source_results)
    message = _collect_messages(*source_results)

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
    # Limita downloads e chamadas Rekognition simultâneas para evitar pico de memória
    semaphore = asyncio.Semaphore(5)

    async def _enrich_one(item: dict) -> None:
        async with semaphore:
            target_bytes = await asyncio.to_thread(_get_target_bytes, item)
            if target_bytes is None:
                item["confidence_rekognition"] = None
                return
            result = await asyncio.to_thread(compare_faces, source_image_bytes, target_bytes)
            item["confidence_rekognition"] = result.get("similarity")

    await asyncio.gather(*(_enrich_one(item) for item in items))
    return items
