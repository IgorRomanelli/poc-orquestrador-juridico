"""
Cliente JUCESP — Junta Comercial do Estado de São Paulo.

DECISÃO DE DESIGN: A JUCESP não expõe API pública e seu site usa JavaScript
client-side, tornando scraping básico inviável sem Playwright. Para a Fase 1
da POC, este módulo gera um link direto de busca e sinaliza revisão manual.
Isso é explícito e documentado — não um fallback silencioso.

Revisão de scraping pode ser considerada em iterações futuras se a taxa de
intervenção manual superar 30% (critério de parada da spec).

Status retornado: sempre "manual_required".
"""

_JUCESP_BASE_URL = "https://www.jucesponline.sp.gov.br"


# ─── função pública ────────────────────────────────────────────────────────────

async def lookup_jucesp(razao_social: str | None, cnpj: str | None) -> dict:
    """
    Retorna link direto para consulta manual na JUCESP Online.

    Sempre retorna requires_manual_review=True — sem exceções.

    Args:
        razao_social: nome da empresa (informativo no retorno).
        cnpj: CNPJ da empresa (informativo no retorno).

    Returns:
        dict com jucesp_search_url e status "manual_required".
    """
    if razao_social or cnpj:
        message = "Consulta JUCESP requer verificação manual — link direto gerado para agilizar"
    else:
        message = "Empresa não identificada — acesse JUCESP manualmente para busca"

    return {
        "razao_social": razao_social,
        "cnpj": cnpj,
        "jucesp_search_url": _JUCESP_BASE_URL,
        "contrato_social_url": None,
        "status": "manual_required",
        "requires_manual_review": True,
        "message": message,
    }
