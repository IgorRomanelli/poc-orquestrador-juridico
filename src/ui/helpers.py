"""
Funções puras de UI — sem dependência do Streamlit.
Extraídas de app.py para permitir testes unitários isolados.
"""

from __future__ import annotations

_SOCIAL_DOMAINS = frozenset({
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "pinterest.com", "linkedin.com",
    "reddit.com", "snapchat.com", "tumblr.com", "flickr.com",
    "threads.net", "vk.com", "t.me",
})

_CLASSIF_PRIORITY = {"pendente": 0, "violacao": 1, "investigar": 2, "nao_violacao": 3}


def is_social(item: dict) -> bool:
    domain = item.get("domain", "").lower()
    return any(social in domain for social in _SOCIAL_DOMAINS)


def site_priority(item: dict) -> int:
    return 1 if is_social(item) else 0


def get_display_image_url(item: dict) -> str:
    """Retorna a melhor URL de imagem disponível para exibição (thumbnail > image_url)."""
    return item.get("preview_thumbnail") or item.get("image_url") or ""


def sort_results(results: list, classifs: dict) -> list:
    """Ordena resultados: classificação → confiança desc (None no final) → tipo de site."""
    def _key(r):
        url = r.get("page_url", "")
        classif = _CLASSIF_PRIORITY.get(classifs.get(url, "pendente"), 0)
        conf = r.get("confidence") if r.get("confidence") is not None else r.get("confidence_rekognition")
        conf_key = -conf if conf is not None else 1.0
        return (classif, conf_key, site_priority(r))
    return sorted(results, key=_key)
