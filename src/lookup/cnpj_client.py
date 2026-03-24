"""
Cliente CNPJ com dupla fonte: BrasilAPI (primária) + receitaws (fallback).

Fluxo:
    1. Valida formato do CNPJ
    2. Aplica delay configurável (CNPJ_REQUEST_DELAY_MS, default 1200ms)
    3. Tenta BrasilAPI → retorna se "found" ou "not_found"
    4. Se BrasilAPI falhar com "error" → fallback automático para receitaws
    5. Retorna resultado com campo "fonte": "brasilapi" | "receitaws"

"not_found" NÃO aciona fallback — ambas as APIs têm a mesma fonte (Receita Federal).

Status possíveis: "found" | "not_found" | "error"
"""

import asyncio
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

_BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
_RECEITAWS_URL = "https://receitaws.com.br/v1/cnpj/{cnpj}"
_CNPJ_PATTERN = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_REQUEST_DELAY_MS = int(os.getenv("CNPJ_REQUEST_DELAY_MS", "300"))
_TIMEOUT_SECONDS = 5.0


# ─── helpers privados ──────────────────────────────────────────────────────────

def _clean_cnpj(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _validate_cnpj_format(digits: str) -> bool:
    return len(digits) == 14


def _format_cnpj(digits: str) -> str:
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _build_address(*parts) -> str | None:
    joined = ", ".join(p for p in parts if p and str(p).strip())
    return joined or None


def _build_empty_result(cnpj_raw: str, status: str, message: str) -> dict:
    """Schema base para resultados sem dados (not_found ou error)."""
    return {
        "cnpj": cnpj_raw,
        "razao_social": None,
        "nome_fantasia": None,
        "situacao": None,
        "atividade_principal": None,
        "logradouro": None,
        "socios": [],
        "telefone": None,
        "email": None,
        "cep": None,
        "bairro": None,
        "natureza_juridica": None,
        "capital_social": None,
        "fonte": None,
        "status": status,
        "requires_manual_review": True,
        "message": message,
    }


def _not_found_result(cnpj_raw: str, message: str) -> dict:
    return _build_empty_result(cnpj_raw, "not_found", message)


def _error_result(cnpj_raw: str, message: str) -> dict:
    return _build_empty_result(cnpj_raw, "error", message)


# ─── clientes internos ────────────────────────────────────────────────────────

async def _lookup_brasilapi(digits: str, formatted: str) -> dict:
    """Consulta BrasilAPI. Retorna found / not_found / error."""
    url = _BRASILAPI_URL.format(cnpj=digits)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return _error_result(formatted, "BrasilAPI timeout após 5s")
    except Exception as exc:
        return _error_result(formatted, f"Erro de conexão BrasilAPI: {exc}")

    if response.status_code == 404:
        return _not_found_result(formatted, "CNPJ não encontrado na Receita Federal — validar manualmente")
    if response.status_code == 429:
        return _error_result(formatted, "BrasilAPI rate limit (429)")
    if response.status_code != 200:
        return _error_result(formatted, f"BrasilAPI HTTP {response.status_code}")

    try:
        data = response.json()
    except Exception:
        return _error_result(formatted, "Resposta inválida da BrasilAPI")

    situacao = data.get("descricao_situacao_cadastral") or data.get("situacao_cadastral")

    socios = [
        f"{s.get('nome_socio', '')} — {s.get('qualificacao_socio', '')}".strip(" —")
        for s in data.get("qsa", [])
        if s.get("nome_socio")
    ]

    telefone = str(data["ddd_telefone_1"]).strip() if data.get("ddd_telefone_1") else None

    return {
        "cnpj": formatted,
        "razao_social": data.get("razao_social"),
        "nome_fantasia": data.get("nome_fantasia") or None,
        "situacao": str(situacao) if situacao is not None else None,
        "atividade_principal": data.get("cnae_fiscal_descricao"),
        "logradouro": _build_address(
            data.get("logradouro"),
            data.get("numero"),
            data.get("bairro"),
            data.get("municipio"),
            data.get("uf"),
        ),
        "socios": socios,
        "telefone": telefone,
        "email": data.get("email") or None,
        "cep": str(data["cep"]).strip() if data.get("cep") else None,
        "bairro": data.get("bairro") or None,
        "natureza_juridica": data.get("natureza_juridica") or None,
        "capital_social": data.get("capital_social"),
        "fonte": "brasilapi",
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }


async def _lookup_receitaws(digits: str, formatted: str) -> dict:
    """Consulta receitaws. Retorna found / not_found / error."""
    url = _RECEITAWS_URL.format(cnpj=digits)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return _error_result(formatted, "receitaws timeout após 5s — validar manualmente")
    except Exception as exc:
        return _error_result(formatted, f"Erro de conexão receitaws: {exc} — validar manualmente")

    if response.status_code == 429:
        return _error_result(formatted, "Erro HTTP 429 — receitaws rate limit. Aguarde e tente novamente")
    if response.status_code == 404:
        return _not_found_result(formatted, "CNPJ não encontrado na Receita Federal — validar manualmente")
    if response.status_code != 200:
        return _error_result(formatted, f"Erro HTTP {response.status_code} na receitaws — validar manualmente")

    try:
        data = response.json()
    except Exception:
        return _error_result(formatted, "Resposta inválida da receitaws — validar manualmente")

    if data.get("status") == "ERROR":
        return _not_found_result(formatted, "CNPJ não encontrado na Receita Federal — validar manualmente")

    situacao = data.get("situacao", "")
    if situacao == "BAIXADA":
        return _not_found_result(formatted, f"Empresa baixada na Receita Federal (situação: {situacao})")

    atividade = None
    atividades = data.get("atividade_principal", [])
    if atividades and isinstance(atividades, list):
        atividade = atividades[0].get("text")

    socios = [
        f"{s.get('nome', '')} — {s.get('qual', '')}".strip(" —")
        for s in data.get("qsa", [])
        if s.get("nome")
    ]

    return {
        "cnpj": formatted,
        "razao_social": data.get("nome"),
        "nome_fantasia": data.get("fantasia") or None,
        "situacao": situacao or None,
        "atividade_principal": atividade,
        "logradouro": _build_address(
            data.get("logradouro"),
            data.get("numero"),
            data.get("complemento"),
            data.get("municipio"),
            data.get("uf"),
        ),
        "socios": socios,
        "telefone": None,
        "email": None,
        "cep": str(data["cep"]).strip() if data.get("cep") else None,
        "bairro": None,
        "natureza_juridica": None,
        "capital_social": None,
        "fonte": "receitaws",
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }


# ─── funções públicas ──────────────────────────────────────────────────────────

async def lookup_cnpj(cnpj: str) -> dict:
    """
    Consulta CNPJ com BrasilAPI (primária) e receitaws (fallback automático).

    Fallback ocorre apenas em caso de erro técnico da BrasilAPI (timeout, 429,
    conexão). "not_found" não aciona fallback — ambas têm a mesma fonte.

    Args:
        cnpj: CNPJ formatado ou apenas dígitos.

    Returns:
        dict com status explícito, requires_manual_review e campo "fonte".
    """
    digits = _clean_cnpj(cnpj)

    if not _validate_cnpj_format(digits):
        return _error_result(cnpj, "CNPJ inválido — formato incorreto")

    formatted = _format_cnpj(digits)

    if _REQUEST_DELAY_MS > 0:
        await asyncio.sleep(_REQUEST_DELAY_MS / 1000)

    result = await _lookup_brasilapi(digits, formatted)

    if result["status"] == "error":
        result = await _lookup_receitaws(digits, formatted)

    return result


async def extract_cnpj_from_text(text: str) -> str | None:
    """
    Extrai o primeiro CNPJ encontrado em um texto livre.

    Args:
        text: texto que pode conter um CNPJ (ex: campo registrant do WHOIS).

    Returns:
        CNPJ como string de dígitos, ou None se não encontrado.
    """
    if not text:
        return None
    match = _CNPJ_PATTERN.search(text)
    if not match:
        return None
    digits = _clean_cnpj(match.group())
    return digits if _validate_cnpj_format(digits) else None
