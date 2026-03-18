"""
Gerador de dossiê em markdown.

Recebe listas de itens classificados (violação / investigar) já enriquecidos
com lookup de domínio e produz o documento estruturado conforme a spec.

Campos ausentes são sempre exibidos como "— não identificado" (nunca omitidos).
"""

from datetime import date as _date
from urllib.parse import quote_plus


# ─── helpers privados ──────────────────────────────────────────────────────────

_PLACEHOLDER = "— não identificado"


def _v(value) -> str:
    """Retorna valor como string ou placeholder se ausente."""
    if value is None or str(value).strip() == "":
        return _PLACEHOLDER
    return str(value).strip()


def _format_socios(socios: list) -> str:
    if not socios:
        return _PLACEHOLDER
    lines = []
    for s in socios:
        if isinstance(s, str):
            lines.append(s)
        elif isinstance(s, dict):
            nome = s.get("nome") or s.get("name") or ""
            qualificacao = s.get("qualificacao") or s.get("qual") or ""
            if qualificacao:
                lines.append(f"{nome} — {qualificacao}")
            else:
                lines.append(nome)
    return "; ".join(filter(None, lines)) or _PLACEHOLDER


def _format_whois_dates(whois: dict) -> str:
    criado = whois.get("created") or whois.get("creation_date")
    expira = whois.get("expiration_date") or whois.get("expires")
    if criado and expira:
        return f"registrado em {criado} / expira em {expira}"
    if criado:
        return f"registrado em {criado}"
    return _PLACEHOLDER


def _format_confidence(item: dict) -> str:
    conf = item.get("confidence")
    source = item.get("source", "")
    if conf is None:
        return _PLACEHOLDER
    pct = f"{int(conf * 100)}%"
    label = "FaceCheck" if source == "facecheck" else "Google Vision"
    return f"{pct} ({label})"


def _maps_url(logradouro: str, municipio: str, uf: str, cep: str) -> str:
    """Retorna URL do Google Maps para o endereço, ou string vazia se desconhecido."""
    if logradouro == _PLACEHOLDER:
        return ""
    parts = [logradouro]
    if municipio:
        parts.append(municipio)
    if uf:
        parts.append(uf)
    if cep != _PLACEHOLDER:
        parts.append(cep)
    query = ", ".join(parts)
    return f"https://maps.google.com/?q={quote_plus(query)}"


def _as_dict(value) -> dict:
    """Garante que o valor é um dict; retorna {} caso contrário."""
    return value if isinstance(value, dict) else {}


def _render_item(index: int, item: dict, label: str = "Violação") -> str:
    """Renderiza um item (violação ou investigação) como bloco markdown."""
    search = _as_dict(item.get("search_result") if isinstance(item, dict) else None)
    lookup = _as_dict(item.get("lookup") if isinstance(item, dict) else None)

    whois = _as_dict(lookup.get("whois"))
    cnpj_data = _as_dict(lookup.get("cnpj_data"))
    jucesp = _as_dict(lookup.get("jucesp"))
    summary = _as_dict(lookup.get("summary"))

    page_url = _v(search.get("page_url"))
    domain = _v(search.get("domain"))
    razao_social = _v(summary.get("razao_social"))
    nome_fantasia = _v(cnpj_data.get("nome_fantasia"))
    cnpj = _v(cnpj_data.get("cnpj") or summary.get("cnpj"))
    socios = _format_socios(cnpj_data.get("socios", []))
    situacao = _v(cnpj_data.get("situacao"))
    natureza_juridica = _v(cnpj_data.get("natureza_juridica"))
    capital_social = _v(cnpj_data.get("capital_social"))
    logradouro = _v(cnpj_data.get("logradouro") or summary.get("address"))
    cep = _v(cnpj_data.get("cep"))
    municipio = cnpj_data.get("municipio") or ""
    uf = cnpj_data.get("uf") or ""
    telefone = _v(cnpj_data.get("telefone"))
    email = _v(cnpj_data.get("email"))
    atividade_principal = _v(cnpj_data.get("atividade_principal"))
    fonte = _v(cnpj_data.get("fonte"))

    endereco = logradouro
    if municipio and logradouro != _PLACEHOLDER:
        endereco = f"{logradouro}, {municipio}/{uf}" if uf else f"{logradouro}, {municipio}"
    if cep != _PLACEHOLDER and municipio:
        endereco = f"{endereco} — CEP {cep}"

    maps_url = _maps_url(logradouro, municipio, uf, cep)
    maps_link = f"[Ver no Google Maps]({maps_url})" if maps_url else _PLACEHOLDER

    whois_dates = _format_whois_dates(whois)
    registrant = _v(whois.get("registrant"))
    jucesp_url = _v(jucesp.get("jucesp_search_url"))
    confidence = _format_confidence(search)

    thumbnail = search.get("preview_thumbnail") or ""
    image_block = (
        f'\n<img src="{thumbnail}" style="max-width:240px;max-height:240px;'
        f'border:1px solid #ccc;margin:6px 0;display:block;">\n'
        if thumbnail.startswith("data:")
        else ""
    )

    return (
        f"### {label} {index}\n"
        f"{image_block}"
        f"- **URL:** {page_url}\n"
        f"- **Domínio:** {domain}\n"
        f"- **Empresa responsável:** {razao_social}\n"
        f"- **Nome fantasia:** {nome_fantasia}\n"
        f"- **CNPJ:** {cnpj}\n"
        f"- **Natureza jurídica:** {natureza_juridica}\n"
        f"- **Capital social:** {capital_social}\n"
        f"- **Atividade principal:** {atividade_principal}\n"
        f"- **Responsável:** {socios}\n"
        f"- **Situação:** {situacao}\n"
        f"- **Endereço:** {endereco}\n"
        f"- **Mapa:** {maps_link}\n"
        f"- **Telefone:** {telefone}\n"
        f"- **E-mail:** {email}\n"
        f"- **WHOIS:** {whois_dates}\n"
        f"- **Registrante WHOIS:** {registrant}\n"
        f"- **JUCESP:** {jucesp_url}\n"
        f"- **Fonte CNPJ:** {fonte}\n"
        f"- **Confiança da busca:** {confidence}\n"
    )


def _render_investigate_item(index: int, item: dict) -> str:
    """Mesmo formato mas com cabeçalho 'Investigação'."""
    return _render_item(index, item, label="Investigação")


# ─── função pública ────────────────────────────────────────────────────────────

def generate(
    client_name: str,
    violations: list[dict],
    investigate: list[dict],
    date: str | None = None,
) -> str:
    """
    Gera markdown completo do dossiê.

    Args:
        client_name: nome do cliente (para o cabeçalho).
        violations: itens marcados como violação.
                    Cada item: {"search_result": dict, "lookup": dict}
        investigate: itens marcados como investigar.
                    Mesmo formato de violations.
        date: data no formato ISO 8601 (default: hoje).

    Returns:
        String markdown completa do dossiê.
    """
    if not date:
        date = str(_date.today())

    sections = [
        "# Dossiê de Violação de Imagem",
        f"**Cliente:** {client_name}",
        f"**Data:** {date}",
        "**Gerado por:** Sistema de Busca de Imagem",
        "",
        "---",
        "",
        "## Violações Identificadas",
        "",
    ]

    if violations:
        for i, item in enumerate(violations, start=1):
            sections.append(_render_item(i, item))
    else:
        sections.append("_Nenhuma violação identificada._\n")

    sections += [
        "---",
        "",
        "## Para Investigação",
        "",
    ]

    if investigate:
        for i, item in enumerate(investigate, start=1):
            sections.append(_render_investigate_item(i, item))
    else:
        sections.append("_Nenhum item para investigação._\n")

    sections += [
        "---",
        f"*Dossiê gerado automaticamente. Curadoria realizada por advogado em {date}.*",
    ]

    return "\n".join(sections)
