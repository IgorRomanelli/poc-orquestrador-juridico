"""
RDAP client — Registration Data Access Protocol.

Consulta https://rdap.org/domain/{domain} para obter dados estruturados de registro
de domínio como alternativa/complemento ao WHOIS tradicional.

Função pública:
    lookup_rdap(domain) → dict com keys: status, registrant, registrar, created,
                          expiration_date, raw
"""

import httpx

_RDAP_BASE = "https://rdap.org/domain"
_TIMEOUT = 3.0


# ─── helpers privados ──────────────────────────────────────────────────────────


def _extract_vcard_field(vcard_array: list, field_name: str) -> str:
    """Extrai campo de um vcardArray pelo nome (ex: 'fn', 'org')."""
    if not vcard_array or len(vcard_array) < 2:
        return ""
    for entry in vcard_array[1]:
        if isinstance(entry, list) and entry and entry[0] == field_name:
            return str(entry[-1]) if entry[-1] else ""
    return ""


def _extract_registrant(data: dict) -> str:
    """Extrai nome do registrante a partir das entidades RDAP."""
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        if "registrant" in roles:
            vcard = entity.get("vcardArray", [])
            name = _extract_vcard_field(vcard, "fn") or _extract_vcard_field(vcard, "org")
            if name:
                return name
    return ""


def _extract_registrar(data: dict) -> str:
    """Extrai nome do registrar a partir das entidades RDAP."""
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        if "registrar" in roles:
            vcard = entity.get("vcardArray", [])
            name = _extract_vcard_field(vcard, "fn") or _extract_vcard_field(vcard, "org")
            if name:
                return name
    return ""


def _extract_date(data: dict, event_action: str) -> str:
    """Extrai data de um evento RDAP (registration, expiration)."""
    for event in data.get("events", []):
        if event.get("eventAction") == event_action:
            raw = event.get("eventDate", "")
            return raw[:10] if raw else ""  # retorna só YYYY-MM-DD
    return ""


def _not_found_result(domain: str) -> dict:
    return {"status": "not_found", "domain": domain}


def _error_result(domain: str, reason: str) -> dict:
    return {"status": "error", "domain": domain, "error": reason}


# ─── função pública ────────────────────────────────────────────────────────────


def lookup_rdap(domain: str) -> dict:
    """
    Consulta RDAP para obter dados de registro do domínio.

    Args:
        domain: nome do domínio (ex: "example.com")

    Returns:
        dict com keys:
            status       : "found" | "not_found" | "error"
            registrant   : nome do registrante (pode ser proxy de privacidade)
            registrar    : nome do registrar
            created      : data de criação (YYYY-MM-DD)
            expiration_date : data de expiração (YYYY-MM-DD)
            raw          : payload JSON completo (apenas quando status="found")
    """
    url = f"{_RDAP_BASE}/{domain}"
    try:
        response = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
    except Exception as exc:
        return _error_result(domain, str(exc))

    if response.status_code == 404:
        return _not_found_result(domain)

    if response.status_code != 200:
        return _error_result(domain, f"HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception as exc:
        return _error_result(domain, f"JSON parse error: {exc}")

    return {
        "status": "found",
        "domain": domain,
        "registrant": _extract_registrant(data),
        "registrar": _extract_registrar(data),
        "created": _extract_date(data, "registration"),
        "expiration_date": _extract_date(data, "expiration"),
        "raw": data,
    }
