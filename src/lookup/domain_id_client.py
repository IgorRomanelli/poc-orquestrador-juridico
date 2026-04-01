"""
Pipeline de identificação de operador para domínios .com sem WHOIS.

Cascata:
    1. crt.sh  — Certificate Transparency logs (grátis, sem autenticação)
    2. Netlas  — WHOIS histórico agregado (50 req/dia grátis, requer NETLAS_API_KEY)
    3. pending — fallback explícito quando ambos falham

Retorno de todas as funções:
    {
        "org": str | None,
        "source": "crt.sh" | "netlas" | "pending",
        "status": "found" | "not_found" | "error" | "pending",
        "requires_manual_review": bool,
        "message": str | None,
    }
"""

import os

import httpx

# CAs conhecidas que não são operadores de sites — filtradas do resultado crt.sh
_KNOWN_CAS: frozenset[str] = frozenset({
    "let's encrypt",
    "letsencrypt",
    "comodo ca limited",
    "comodo",
    "digicert",
    "globalsign",
    "sectigo",
    "godaddy",
    "entrust",
    "verisign",
    "thawte",
    "rapidssl",
    "geotrust",
    "amazon",
    "cloudflare",
    "microsoft",
    "google",
    "zerossl",
})

_CRT_SH_URL = "https://crt.sh/?q={domain}&output=json"
_NETLAS_WHOIS_URL = "https://app.netlas.io/api/whois_domains/"


def _is_known_ca(org: str) -> bool:
    """Retorna True se org é uma CA conhecida (não é operador do site)."""
    return any(ca in org.lower() for ca in _KNOWN_CAS)


async def lookup_by_certs(domain: str) -> dict:
    """
    Consulta crt.sh para identificar a organização no cert SSL mais recente.
    Filtra CAs conhecidas e retorna apenas organizações que são operadores reais.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(_CRT_SH_URL.format(domain=domain))
    except Exception as exc:
        return {
            "org": None,
            "source": "crt.sh",
            "status": "error",
            "requires_manual_review": True,
            "message": f"crt.sh erro: {exc} — validar manualmente",
        }

    if response.status_code != 200:
        return {
            "org": None,
            "source": "crt.sh",
            "status": "error",
            "requires_manual_review": True,
            "message": f"crt.sh HTTP {response.status_code} — validar manualmente",
        }

    try:
        records = response.json()
    except Exception:
        return {
            "org": None,
            "source": "crt.sh",
            "status": "error",
            "requires_manual_review": True,
            "message": "crt.sh resposta inválida (JSON malformado) — validar manualmente",
        }
    if not records:
        return {
            "org": None,
            "source": "crt.sh",
            "status": "not_found",
            "requires_manual_review": True,
            "message": "crt.sh sem certificados para este domínio — validar manualmente",
        }

    for record in records:
        org = record.get("subject_o") or ""
        if org and not _is_known_ca(org):
            return {
                "org": org.strip(),
                "source": "crt.sh",
                "status": "found",
                "requires_manual_review": False,
                "message": None,
            }

    return {
        "org": None,
        "source": "crt.sh",
        "status": "not_found",
        "requires_manual_review": True,
        "message": "crt.sh: apenas CAs encontradas, nenhum operador identificado — validar manualmente",
    }


async def lookup_by_netlas(domain: str, api_key: str) -> dict:
    """
    Consulta Netlas.io WHOIS histórico para identificar o operador registrado.
    Requer NETLAS_API_KEY no ambiente (50 req/dia no free tier).
    """
    params = {"q": f"domain:{domain}", "fields": "registrant_organization,registrant_name"}
    headers = {"X-Api-Key": api_key}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_NETLAS_WHOIS_URL, params=params, headers=headers)
    except Exception as exc:
        return {
            "org": None,
            "source": "netlas",
            "status": "error",
            "requires_manual_review": True,
            "message": f"netlas erro: {exc} — validar manualmente",
        }

    if response.status_code == 401:
        return {
            "org": None,
            "source": "netlas",
            "status": "error",
            "requires_manual_review": True,
            "message": "Netlas: autenticação falhou (NETLAS_API_KEY inválida) — validar manualmente",
        }

    if response.status_code != 200:
        return {
            "org": None,
            "source": "netlas",
            "status": "error",
            "requires_manual_review": True,
            "message": f"Netlas HTTP {response.status_code} — validar manualmente",
        }

    try:
        data = response.json()
    except Exception:
        return {
            "org": None,
            "source": "netlas",
            "status": "error",
            "requires_manual_review": True,
            "message": "Netlas resposta inválida (JSON malformado) — validar manualmente",
        }
    items = data.get("items") or []
    if not items:
        return {
            "org": None,
            "source": "netlas",
            "status": "not_found",
            "requires_manual_review": True,
            "message": "Netlas: nenhum registro histórico encontrado — validar manualmente",
        }

    first = items[0].get("data") or {}
    org = first.get("registrant_organization") or first.get("registrant_name")
    if not org:
        return {
            "org": None,
            "source": "netlas",
            "status": "not_found",
            "requires_manual_review": True,
            "message": "Netlas: registro encontrado mas sem organização/nome — validar manualmente",
        }

    return {
        "org": org.strip(),
        "source": "netlas",
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }


async def identify_domain_operator(domain: str) -> dict:
    """
    Pipeline completo: crt.sh → Netlas.io → pending.
    Sempre retorna dict explícito — nunca None.
    """
    crt_result = await lookup_by_certs(domain)
    if crt_result["status"] == "found":
        return crt_result

    netlas_key = os.environ.get("NETLAS_API_KEY")
    if netlas_key:
        netlas_result = await lookup_by_netlas(domain, api_key=netlas_key)
        if netlas_result["status"] == "found":
            return netlas_result

    return {
        "org": None,
        "source": "pending",
        "status": "pending",
        "requires_manual_review": True,
        "message": (
            "Operador não identificado automaticamente — "
            "CNPJ requer verificação manual no site ou scraping assíncrono"
        ),
    }
