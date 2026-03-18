"""
Agregador de resultados de busca de imagem.

Recebe os resultados brutos de FaceCheck e Google Vision e produz
uma lista unificada, deduplicada e ordenada por relevância.

Regra de deduplicação: por page_url exato.
Quando o mesmo domínio aparece nas duas APIs com page_urls distintos, ambos são mantidos.
"""

from urllib.parse import urlparse


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
