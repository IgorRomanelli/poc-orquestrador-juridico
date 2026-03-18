"""
Cliente WHOIS para consulta de dados de registro de domínio.

Retorna estrutura explícita em todos os casos — nunca silencia erros.
Status possíveis: "found" | "not_found" | "error"
"""

import asyncio
import re
from datetime import datetime

import whois

_OWNER_ID_RE = re.compile(r"ownerid:\s*(\S+)", re.IGNORECASE)
_RESPONSIBLE_RE = re.compile(r"responsible:\s*(.+)", re.IGNORECASE)
_CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_REGISTROBR_WHOIS_URL = "https://registro.br/tecnologia/ferramentas/whois?search={domain}"
# Captura blocos nic-hdl-br com person e e-mail
_CONTACT_BLOCK_RE = re.compile(
    r"nic-hdl-br:\s*(\S+).*?person:\s*(.+?)\s*\ne-mail:\s*(\S+)",
    re.IGNORECASE | re.DOTALL,
)


# ─── privacy proxy detection ───────────────────────────────────────────────────

_PRIVACY_PROXIES: frozenset[str] = frozenset({
    "domains by proxy",
    "whoisguard",
    "privacyprotect",
    "perfect privacy",
    "contact privacy",
    "privacy protect",
    "registrant privacy",
    "withheld for privacy",
    "data protected",
    "redacted for privacy",
})


def _is_privacy_proxy(registrant: str | None) -> bool:
    """Retorna True se o registrant é um serviço de privacidade/proxy."""
    if not registrant:
        return False
    lower = registrant.lower()
    return any(proxy in lower for proxy in _PRIVACY_PROXIES)


# ─── helpers privados ──────────────────────────────────────────────────────────

def _normalize_date(value) -> str | None:
    """Normaliza datetime, lista de datetime ou None para string ISO 8601."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        return value
    return None


def _extract_field(parsed, *keys):
    """Tenta múltiplos atributos no objeto WHOIS (inconsistente entre TLDs)."""
    for key in keys:
        val = getattr(parsed, key, None)
        if val:
            if isinstance(val, list):
                val = val[0] if val else None
            if val:
                return str(val).strip()
    return None


def _extract_contacts(raw_text: str) -> dict:
    """
    Extrai responsible e blocos de contato (nic-hdl-br) do texto bruto do WHOIS.
    Retorna {"responsible": str|None, "contacts": [{"id", "name", "email"}]}
    """
    responsible = None
    m = _RESPONSIBLE_RE.search(raw_text)
    if m:
        responsible = m.group(1).strip()

    contacts = []
    for match in _CONTACT_BLOCK_RE.finditer(raw_text):
        contacts.append({
            "id": match.group(1).strip(),
            "name": match.group(2).strip(),
            "email": match.group(3).strip(),
        })

    return {"responsible": responsible, "contacts": contacts}


def _extract_document(parsed) -> str | None:
    """
    Extrai o CNPJ do campo owner-id do WHOIS do Registro.br.
    O campo 'DOCUMENTO' exibido no site mapeia para 'owner-id:' no texto bruto.
    """
    raw_text = getattr(parsed, "text", None) or ""
    match = _OWNER_ID_RE.search(raw_text)
    if match:
        candidate = match.group(1).strip()
        if _CNPJ_RE.match(candidate):
            return candidate
    return None


def _not_found_result(domain: str, message: str) -> dict:
    return {
        "domain": domain,
        "registrant": None,
        "responsible": None,
        "contacts": [],
        "registrant_email": None,
        "registrar": None,
        "creation_date": None,
        "expiration_date": None,
        "name_servers": [],
        "document": None,
        "registrobr_url": _REGISTROBR_WHOIS_URL.format(domain=domain),
        "status": "not_found",
        "requires_manual_review": True,
        "message": message,
    }


def _error_result(domain: str, message: str) -> dict:
    return {
        "domain": domain,
        "registrant": None,
        "responsible": None,
        "contacts": [],
        "registrant_email": None,
        "registrar": None,
        "creation_date": None,
        "expiration_date": None,
        "name_servers": [],
        "document": None,
        "registrobr_url": _REGISTROBR_WHOIS_URL.format(domain=domain),
        "status": "error",
        "requires_manual_review": True,
        "message": message,
    }


# ─── função pública ────────────────────────────────────────────────────────────

async def lookup_whois(domain: str) -> dict:
    """
    Consulta WHOIS de um domínio de forma assíncrona.

    Args:
        domain: domínio a consultar (ex: "exemplo.com.br")

    Returns:
        dict com status explícito e requires_manual_review.
    """
    try:
        parsed = await asyncio.wait_for(
            asyncio.to_thread(whois.whois, domain),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        return _error_result(domain, "WHOIS timeout após 10s — validar manualmente")
    except Exception as exc:
        return _error_result(domain, f"WHOIS erro inesperado: {exc} — validar manualmente")

    if parsed is None:
        return _not_found_result(domain, "WHOIS sem resposta — validar manualmente")

    registrant = _extract_field(parsed, "org", "name", "registrant_name", "registrant")
    registrant_email = _extract_field(parsed, "emails", "registrant_email")

    # emails pode ser lista
    raw_emails = getattr(parsed, "emails", None)
    if isinstance(raw_emails, list) and raw_emails:
        registrant_email = raw_emails[0]

    name_servers = getattr(parsed, "name_servers", []) or []
    if isinstance(name_servers, str):
        name_servers = [name_servers]
    name_servers = [ns.lower() for ns in name_servers if ns]

    creation_date = _normalize_date(getattr(parsed, "creation_date", None))
    expiration_date = _normalize_date(getattr(parsed, "expiration_date", None))
    registrar = _extract_field(parsed, "registrar", "sponsoring_registrar")

    if not registrant and not registrar and not creation_date:
        return _not_found_result(
            domain,
            "WHOIS sem dados de registrante — validar manualmente",
        )

    raw_text = getattr(parsed, "text", "") or ""
    document = _extract_document(parsed)
    contact_data = _extract_contacts(raw_text)

    return {
        "domain": domain,
        "registrant": registrant,
        "responsible": contact_data["responsible"],
        "contacts": contact_data["contacts"],
        "registrant_email": registrant_email,
        "registrar": registrar,
        "creation_date": creation_date,
        "expiration_date": expiration_date,
        "name_servers": name_servers,
        "document": document,
        "registrobr_url": _REGISTROBR_WHOIS_URL.format(domain=domain),
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }
