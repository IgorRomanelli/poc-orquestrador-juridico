"""
Orquestrador de lookup: coordena WHOIS, CNPJ e JUCESP para um domínio.

Fluxo:
    1. lookup_whois(domain)           → sequencial (CNPJ depende do registrant)
    2. asyncio.gather(
           lookup_cnpj(cnpj),         → paralelo
           lookup_jucesp(name, cnpj)  → paralelo
       )

Status global: "found" | "partial" | "not_found" | "error"
"""

import asyncio

from .cnpj_client import extract_cnpj_from_text, lookup_cnpj
from .domain_id_client import identify_domain_operator
from .rdap_client import lookup_rdap
from .whois_client import _is_privacy_proxy, lookup_whois


def _is_br_domain(domain: str) -> bool:
    """Retorna True se o domínio é .br (registrado no Registro.br)."""
    return domain.strip().lower().endswith(".br")


# ─── helpers privados ──────────────────────────────────────────────────────────

def _compute_global_status(whois: dict, cnpj: dict) -> str:
    whois_ok = whois.get("status") == "found"
    cnpj_ok = cnpj.get("status") == "found"
    has_error = whois.get("status") == "error" or cnpj.get("status") == "error"

    if whois_ok and cnpj_ok:
        return "found"
    if has_error:
        return "error"
    if whois_ok or cnpj_ok:
        return "partial"
    return "not_found"


def _collect_review_reasons(whois: dict, cnpj: dict) -> list[str]:
    reasons = []
    for result in (whois, cnpj):
        msg = result.get("message")
        if result.get("requires_manual_review") and msg:
            reasons.append(msg)
    return reasons


def _build_summary(whois: dict, cnpj: dict, domain_id: dict | None = None) -> dict:
    razao_social = cnpj.get("razao_social") or whois.get("registrant")
    if not razao_social and domain_id and domain_id.get("org"):
        razao_social = domain_id["org"]
    return {
        "razao_social": razao_social,
        "cnpj": cnpj.get("cnpj"),
        "registrant": whois.get("registrant"),
        "address": cnpj.get("logradouro"),
        "socios": cnpj.get("socios", []),
        "manual_review_reasons": _collect_review_reasons(whois, cnpj),
    }


def _exception_to_error(exc: Exception, label: str) -> dict:
    return {
        "status": "error",
        "requires_manual_review": True,
        "message": f"{label} falhou com erro inesperado: {exc} — validar manualmente",
    }


# ─── função pública ────────────────────────────────────────────────────────────

async def lookup_domain(domain: str) -> dict:
    """
    Executa lookup completo de um domínio: WHOIS + CNPJ + JUCESP.

    Args:
        domain: domínio a consultar (ex: "exemplo.com.br").

    Returns:
        dict com status global, sub-resultados e summary consolidado.
    """
    # Passo 1: WHOIS (sequencial — resultado alimenta CNPJ)
    whois_result = await lookup_whois(domain)

    # Passo 1b: RDAP como complemento para domínios .com/.net com privacy proxy
    if not _is_br_domain(domain) and _is_privacy_proxy(whois_result.get("registrant")):
        rdap = await asyncio.to_thread(lookup_rdap, domain)
        if rdap.get("status") == "found":
            whois_result["registrant_rdap"] = rdap.get("registrant", "")
            whois_result["registrar_rdap"] = rdap.get("registrar", "")
            whois_result["privacy_proxy"] = True
            if not whois_result.get("creation_date"):
                whois_result["creation_date"] = rdap.get("created")
            if not whois_result.get("expiration_date"):
                whois_result["expiration_date"] = rdap.get("expiration_date")

    # Passo 1c: pipeline crt.sh → Netlas para .com sem registrante útil
    domain_id_result = None
    is_com_domain = domain.strip().lower().endswith(".com") and not _is_br_domain(domain)
    registrant_after_rdap = whois_result.get("registrant")
    has_useful_registrant = bool(registrant_after_rdap) and not _is_privacy_proxy(registrant_after_rdap)

    if is_com_domain and not has_useful_registrant:
        domain_id_result = await identify_domain_operator(domain)

    # Extrair CNPJ: prioriza campo owner-id do Registro.br, fallback para regex no texto
    registrant = whois_result.get("registrant")
    registrant_email = whois_result.get("registrant_email")
    cnpj_candidate = whois_result.get("document")
    if not cnpj_candidate:
        search_text = " ".join(filter(None, [registrant, registrant_email]))
        cnpj_candidate = await extract_cnpj_from_text(search_text)

    # Passo 2: CNPJ
    cnpj_coro = lookup_cnpj(cnpj_candidate) if cnpj_candidate else _no_cnpj_result(domain)

    try:
        cnpj_result = await cnpj_coro
    except Exception as exc:
        cnpj_result = _exception_to_error(exc, "CNPJ")

    global_status = _compute_global_status(whois_result, cnpj_result)
    requires_manual = any(
        r.get("requires_manual_review")
        for r in (whois_result, cnpj_result)
    )

    return {
        "domain": domain,
        "status": global_status,
        "requires_manual_review": requires_manual,
        "whois": whois_result,
        "cnpj_data": cnpj_result,
        "domain_id": domain_id_result,
        "summary": _build_summary(whois_result, cnpj_result, domain_id_result),
    }


async def _no_cnpj_result(domain: str) -> dict:
    """
    Resultado padrão quando nenhum CNPJ é extraído do WHOIS.
    Declarada async para compatibilidade com asyncio.gather em lookup_domain — sem I/O.
    """
    return {
        "cnpj": None,
        "razao_social": None,
        "nome_fantasia": None,
        "situacao": None,
        "atividade_principal": None,
        "logradouro": None,
        "socios": [],
        "status": "not_found",
        "requires_manual_review": True,
        "message": "CNPJ não encontrado no WHOIS — validar manualmente",
    }
