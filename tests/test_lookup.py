"""
Testes para o módulo de lookup (Hipótese 2).

Seção 1 — Testes unitários (sem I/O real, rodam sempre)
Seção 2 — Testes de integração (requerem domínios reais, skipados por padrão)

Critério de sucesso H2: ≥ 70% dos domínios retornam status "found" ou "partial"
sem intervenção manual (definido em specs/poc-tecnica.md).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ══════════════════════════════════════════════════════════════════════════════
# Seção 1 — Testes unitários (sem I/O)
# ══════════════════════════════════════════════════════════════════════════════

# ─── whois_client ─────────────────────────────────────────────────────────────

class TestWhoisClient:

    async def test_found_returns_required_keys(self):
        """Resultado "found" contém todas as chaves obrigatórias."""
        from src.lookup.whois_client import lookup_whois

        fake_parsed = MagicMock()
        fake_parsed.org = "Empresa Exemplo Ltda"
        fake_parsed.emails = "contato@exemplo.com.br"
        fake_parsed.registrar = "Registro.br"
        fake_parsed.creation_date = None
        fake_parsed.expiration_date = None
        fake_parsed.name_servers = ["ns1.exemplo.com.br"]
        fake_parsed.text = ""  # sem CNPJ no texto bruto deste mock

        with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "found"
        assert result["requires_manual_review"] is False
        assert result["domain"] == "exemplo.com.br"
        assert result["registrant"] == "Empresa Exemplo Ltda"
        assert result["document"] is None  # texto bruto sem owner-id
        for key in ("registrant", "registrant_email", "registrar", "creation_date",
                    "expiration_date", "name_servers", "document", "status", "requires_manual_review", "message"):
            assert key in result, f"Chave ausente: {key}"

    async def test_empty_whois_returns_not_found(self):
        """WHOIS sem dados retorna status not_found e requires_manual_review=True."""
        from src.lookup.whois_client import lookup_whois

        fake_parsed = MagicMock()
        fake_parsed.org = None
        fake_parsed.name = None
        fake_parsed.registrant_name = None
        fake_parsed.registrant = None
        fake_parsed.emails = None
        fake_parsed.registrant_email = None
        fake_parsed.registrar = None
        fake_parsed.sponsoring_registrar = None
        fake_parsed.creation_date = None
        fake_parsed.expiration_date = None
        fake_parsed.name_servers = []

        with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
            result = await lookup_whois("dominio-inexistente.com.br")

        assert result["status"] == "not_found"
        assert result["requires_manual_review"] is True
        assert result["message"] is not None

    async def test_none_response_returns_not_found(self):
        """Resposta None do whois retorna not_found."""
        from src.lookup.whois_client import lookup_whois

        with patch("src.lookup.whois_client.whois.whois", return_value=None):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "not_found"
        assert result["requires_manual_review"] is True

    async def test_timeout_returns_error(self):
        """Timeout retorna status error com requires_manual_review=True."""
        from src.lookup.whois_client import lookup_whois

        with patch("src.lookup.whois_client.whois.whois", side_effect=asyncio.TimeoutError()):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "timeout" in result["message"].lower()

    async def test_unexpected_exception_returns_error(self):
        """Exceção genérica retorna status error."""
        from src.lookup.whois_client import lookup_whois

        with patch("src.lookup.whois_client.whois.whois", side_effect=ConnectionError("falhou")):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True

    async def test_extracts_cnpj_from_owner_id_field(self):
        """WHOIS com campo owner-id contendo CNPJ preenche 'document'."""
        from src.lookup.whois_client import lookup_whois

        fake_parsed = MagicMock()
        fake_parsed.org = "Empresa Exemplo Ltda"
        fake_parsed.emails = "contato@exemplo.com.br"
        fake_parsed.registrar = "Registro.br"
        fake_parsed.creation_date = None
        fake_parsed.expiration_date = None
        fake_parsed.name_servers = ["ns1.exemplo.com.br"]
        # Texto bruto simulando campo owner-id do Registro.br
        fake_parsed.text = (
            "domain: exemplo.com.br\n"
            "ownerid: 11.222.333/0001-81\n"
            "owner: Empresa Exemplo Ltda\n"
        )

        with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "found"
        assert result["document"] == "11.222.333/0001-81"

    async def test_extracts_contacts_from_nic_hdl_br_block(self):
        """Bloco nic-hdl-br com person e e-mail é extraído para 'contacts'."""
        from src.lookup.whois_client import lookup_whois

        fake_parsed = MagicMock()
        fake_parsed.org = "Empresa Exemplo Ltda"
        fake_parsed.emails = "contato@exemplo.com.br"
        fake_parsed.registrar = "Registro.br"
        fake_parsed.creation_date = None
        fake_parsed.expiration_date = None
        fake_parsed.name_servers = []
        fake_parsed.text = (
            "nic-hdl-br: ABC123\n"
            "person: João da Silva\n"
            "e-mail: joao@exemplo.com.br\n"
            "country: BR\n"
        )

        with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
            result = await lookup_whois("exemplo.com.br")

        assert result["status"] == "found"
        assert len(result["contacts"]) == 1
        assert result["contacts"][0]["name"] == "João da Silva"
        assert result["contacts"][0]["email"] == "joao@exemplo.com.br"
        assert result["contacts"][0]["id"] == "ABC123"


# ─── cnpj_client ──────────────────────────────────────────────────────────────

def _make_brasilapi_found():
    return {
        "cnpj": "11.222.333/0001-81",
        "razao_social": "Empresa Exemplo Ltda",
        "nome_fantasia": "Exemplo",
        "situacao": "ATIVA",
        "atividade_principal": "Desenvolvimento de software",
        "logradouro": "Rua das Flores, 123, São Paulo, SP",
        "socios": ["João Silva — Sócio Administrador"],
        "telefone": "1133334444",
        "email": "contato@exemplo.com.br",
        "cep": "01310100",
        "bairro": "Centro",
        "natureza_juridica": "Sociedade Empresária Limitada",
        "capital_social": 100000.0,
        "fonte": "brasilapi",
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }


def _make_receitaws_found():
    return {
        "cnpj": "11.222.333/0001-81",
        "razao_social": "Empresa Exemplo Ltda",
        "nome_fantasia": "Exemplo",
        "situacao": "ATIVA",
        "atividade_principal": "Desenvolvimento de software",
        "logradouro": "Rua das Flores, 123, São Paulo, SP",
        "socios": ["João Silva — Sócio Administrador"],
        "telefone": None,
        "email": None,
        "cep": None,
        "bairro": None,
        "natureza_juridica": None,
        "capital_social": None,
        "fonte": "receitaws",
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }


class TestCnpjClient:

    async def test_found_returns_required_keys(self):
        """BrasilAPI found retorna todas as chaves obrigatórias incluindo campos extras."""
        from src.lookup.cnpj_client import lookup_cnpj

        with (
            patch("src.lookup.cnpj_client._lookup_brasilapi", new=AsyncMock(return_value=_make_brasilapi_found())),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await lookup_cnpj("11222333000181")

        assert result["status"] == "found"
        assert result["requires_manual_review"] is False
        assert result["razao_social"] == "Empresa Exemplo Ltda"
        assert result["fonte"] == "brasilapi"
        for key in ("cnpj", "razao_social", "nome_fantasia", "situacao", "atividade_principal",
                    "logradouro", "socios", "telefone", "email", "cep", "bairro",
                    "natureza_juridica", "capital_social", "fonte",
                    "status", "requires_manual_review", "message"):
            assert key in result, f"Chave ausente: {key}"

    async def test_invalid_cnpj_format_returns_error(self):
        """CNPJ com formato inválido retorna error sem chamada HTTP."""
        from src.lookup.cnpj_client import lookup_cnpj

        result = await lookup_cnpj("123")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "inválido" in result["message"].lower()

    async def test_404_returns_not_found(self):
        """BrasilAPI 404 retorna not_found sem acionar fallback."""
        from src.lookup.cnpj_client import lookup_cnpj

        not_found = {
            "cnpj": "11.222.333/0001-81",
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
            "status": "not_found",
            "requires_manual_review": True,
            "message": "CNPJ não encontrado na Receita Federal — validar manualmente",
        }

        with (
            patch("src.lookup.cnpj_client._lookup_brasilapi", new=AsyncMock(return_value=not_found)),
            patch("src.lookup.cnpj_client._lookup_receitaws", new=AsyncMock()) as mock_receitaws,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await lookup_cnpj("11222333000181")

        assert result["status"] == "not_found"
        assert result["requires_manual_review"] is True
        mock_receitaws.assert_not_called()  # fallback NÃO acionado para not_found

    async def test_429_returns_error_with_rate_limit_message(self):
        """BrasilAPI 429 aciona fallback; se receitaws também falhar, retorna error."""
        from src.lookup.cnpj_client import lookup_cnpj

        brasilapi_error = {
            **_make_brasilapi_found(),
            "fonte": None,
            "status": "error",
            "requires_manual_review": True,
            "message": "BrasilAPI rate limit (429)",
        }
        receitaws_error = {
            **_make_receitaws_found(),
            "fonte": None,
            "status": "error",
            "requires_manual_review": True,
            "message": "Erro HTTP 429 — receitaws rate limit. Aguarde e tente novamente",
        }

        with (
            patch("src.lookup.cnpj_client._lookup_brasilapi", new=AsyncMock(return_value=brasilapi_error)),
            patch("src.lookup.cnpj_client._lookup_receitaws", new=AsyncMock(return_value=receitaws_error)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await lookup_cnpj("11222333000181")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "rate limit" in result["message"].lower()

    async def test_brasilapi_error_falls_back_to_receitaws(self):
        """BrasilAPI error aciona fallback para receitaws; resultado final é found com fonte receitaws."""
        from src.lookup.cnpj_client import lookup_cnpj

        brasilapi_error = {
            **_make_brasilapi_found(),
            "fonte": None,
            "status": "error",
            "requires_manual_review": True,
            "message": "BrasilAPI rate limit (429)",
        }

        with (
            patch("src.lookup.cnpj_client._lookup_brasilapi", new=AsyncMock(return_value=brasilapi_error)),
            patch("src.lookup.cnpj_client._lookup_receitaws", new=AsyncMock(return_value=_make_receitaws_found())),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await lookup_cnpj("11222333000181")

        assert result["status"] == "found"
        assert result["fonte"] == "receitaws"
        assert result["requires_manual_review"] is False

    async def test_fonte_field_always_present(self):
        """Campo 'fonte' está presente em todos os resultados (found, not_found, error)."""
        from src.lookup.cnpj_client import lookup_cnpj

        # CNPJ inválido → error sem HTTP
        result = await lookup_cnpj("123")
        assert "fonte" in result

        # BrasilAPI found
        with (
            patch("src.lookup.cnpj_client._lookup_brasilapi", new=AsyncMock(return_value=_make_brasilapi_found())),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await lookup_cnpj("11222333000181")
        assert "fonte" in result

    async def test_extract_cnpj_from_text_valid(self):
        """Extrai CNPJ de texto com formato válido."""
        from src.lookup.cnpj_client import extract_cnpj_from_text

        result = await extract_cnpj_from_text("Empresa registrada com CNPJ 11.222.333/0001-81")
        assert result == "11222333000181"

    async def test_extract_cnpj_from_text_no_cnpj(self):
        """Retorna None quando não há CNPJ no texto."""
        from src.lookup.cnpj_client import extract_cnpj_from_text

        result = await extract_cnpj_from_text("sem cnpj aqui")
        assert result is None

    async def test_extract_cnpj_from_text_empty(self):
        """Retorna None para texto vazio ou None."""
        from src.lookup.cnpj_client import extract_cnpj_from_text

        assert await extract_cnpj_from_text("") is None
        assert await extract_cnpj_from_text(None) is None


# ─── orchestrator ─────────────────────────────────────────────────────────────

class TestOrchestrator:

    def _make_whois_found(self):
        return {
            "domain": "exemplo.com.br",
            "registrant": "Empresa Ltda",
            "registrant_email": "contato@exemplo.com.br",
            "registrar": "Registro.br",
            "creation_date": "2020-01-01",
            "expiration_date": "2026-01-01",
            "name_servers": ["ns1.exemplo.com.br"],
            "status": "found",
            "requires_manual_review": False,
            "message": None,
        }

    def _make_cnpj_found(self):
        return {
            "cnpj": "11.222.333/0001-81",
            "razao_social": "Empresa Ltda",
            "nome_fantasia": None,
            "situacao": "ATIVA",
            "atividade_principal": "Desenvolvimento de software",
            "logradouro": "Rua das Flores, 123, São Paulo/SP",
            "socios": ["João Silva — Sócio Administrador"],
            "status": "found",
            "requires_manual_review": False,
            "message": None,
        }

    async def test_combines_all_results(self):
        """Orchestrator combina WHOIS + CNPJ em estrutura unificada."""
        from src.lookup.orchestrator import lookup_domain

        with (
            patch("src.lookup.orchestrator.lookup_whois", return_value=self._make_whois_found()),
            patch("src.lookup.orchestrator.extract_cnpj_from_text", return_value="11222333000181"),
            patch("src.lookup.orchestrator.lookup_cnpj", return_value=self._make_cnpj_found()),
        ):
            result = await lookup_domain("exemplo.com.br")

        assert result["domain"] == "exemplo.com.br"
        assert result["status"] == "found"
        assert "whois" in result
        assert "cnpj_data" in result
        assert "summary" in result
        assert result["summary"]["razao_social"] == "Empresa Ltda"
        assert result["summary"]["cnpj"] == "11.222.333/0001-81"

    async def test_partial_when_cnpj_missing(self):
        """Status é 'partial' quando WHOIS encontrado mas CNPJ não."""
        from src.lookup.orchestrator import lookup_domain

        with (
            patch("src.lookup.orchestrator.lookup_whois", return_value=self._make_whois_found()),
            patch("src.lookup.orchestrator.extract_cnpj_from_text", return_value=None),
        ):
            result = await lookup_domain("exemplo.com.br")

        assert result["status"] == "partial"
        assert result["requires_manual_review"] is True

    async def test_error_isolation_when_cnpj_raises(self):
        """Exceção no CNPJ não cancela o resultado do WHOIS."""
        from src.lookup.orchestrator import lookup_domain

        with (
            patch("src.lookup.orchestrator.lookup_whois", return_value=self._make_whois_found()),
            patch("src.lookup.orchestrator.extract_cnpj_from_text", return_value="11222333000181"),
            patch("src.lookup.orchestrator.lookup_cnpj", side_effect=RuntimeError("falha")),
        ):
            result = await lookup_domain("exemplo.com.br")

        assert result["whois"]["status"] == "found"
        assert result["status"] == "error"
        assert result["requires_manual_review"] is True

    async def test_summary_uses_cnpj_razao_social_when_available(self):
        """summary.razao_social prioriza CNPJ sobre WHOIS registrant."""
        from src.lookup.orchestrator import lookup_domain

        whois = {**self._make_whois_found(), "registrant": "Nome Diferente"}
        cnpj = {**self._make_cnpj_found(), "razao_social": "Empresa Oficial Ltda"}

        with (
            patch("src.lookup.orchestrator.lookup_whois", return_value=whois),
            patch("src.lookup.orchestrator.extract_cnpj_from_text", return_value="11222333000181"),
            patch("src.lookup.orchestrator.lookup_cnpj", return_value=cnpj),
        ):
            result = await lookup_domain("exemplo.com.br")

        assert result["summary"]["razao_social"] == "Empresa Oficial Ltda"


# ══════════════════════════════════════════════════════════════════════════════
# Seção 2 — Testes de integração com domínios reais (skipados por padrão)
#
# Como usar:
#   1. Preencha CLOSED_CASE_DOMAINS com domínios de casos encerrados do Ulysses
#   2. Execute: pytest tests/test_lookup.py -m integration -s
# ══════════════════════════════════════════════════════════════════════════════

CLOSED_CASE_DOMAINS: list[str] = []
# Preencher com domínios de casos encerrados do Ulysses antes de rodar


@pytest.mark.skipif(not CLOSED_CASE_DOMAINS, reason="Nenhum domínio real fornecido")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_domain_lookup_h2_criterion():
    """
    Valida critério de sucesso H2: ≥ 70% sem intervenção manual.
    Requer domínios de casos encerrados do Ulysses em CLOSED_CASE_DOMAINS.
    """
    from src.lookup.orchestrator import lookup_domain

    results = []
    for domain in CLOSED_CASE_DOMAINS:
        result = await lookup_domain(domain)
        results.append(result)

        w = result["whois"]
        c = result["cnpj_data"]

        print(f"\n{'='*60}")
        print(f"DOMÍNIO: {domain}")
        print(f"STATUS GERAL: {result['status']} | revisão manual: {result['requires_manual_review']}")

        print(f"\n── WHOIS ({w['status']})")
        print(f"   Registrante:  {w.get('registrant')}")
        print(f"   Responsável:  {w.get('responsible')}")
        print(f"   Documento:    {w.get('document')}")
        print(f"   Criado em:    {w.get('creation_date')}")
        print(f"   Expira em:    {w.get('expiration_date')}")
        for ct in w.get('contacts', []):
            print(f"   Contato [{ct['id']}]: {ct['name']} <{ct['email']}>")
        print(f"   Registro.br:  {w.get('registrobr_url')}")
        if w.get('message'):
            print(f"   ⚠ {w['message']}")

        print(f"\n── CNPJ ({c['status']})")
        print(f"   CNPJ:         {c.get('cnpj')}")
        print(f"   Razão social: {c.get('razao_social')}")
        print(f"   Fantasia:     {c.get('nome_fantasia')}")
        print(f"   Situação:     {c.get('situacao')}")
        print(f"   Atividade:    {c.get('atividade_principal')}")
        print(f"   Endereço:     {c.get('logradouro')}")
        print(f"   CEP:          {c.get('cep') or '—'}")
        print(f"   Telefone:     {c.get('telefone') or '—'}")
        print(f"   E-mail:       {c.get('email') or '—'}")
        print(f"   Nat. jurídica:{c.get('natureza_juridica') or '—'}")
        print(f"   Capital soc.: {c.get('capital_social') or '—'}")
        print(f"   Fonte:        {c.get('fonte') or '—'}")
        print(f"   Sócios:       {', '.join(c.get('socios', [])) or '—'}")
        if c.get('message'):
            print(f"   ⚠ {c['message']}")

    # Garantir que nenhum resultado tem campos ausentes
    for r in results:
        for key in ("domain", "status", "requires_manual_review", "whois", "cnpj_data", "summary"):
            assert key in r, f"Chave ausente no resultado de {r.get('domain')}: {key}"

    # Critério H2: ≥ 70% com status found ou partial (sem necessidade de intervenção além da JUCESP)
    success = [r for r in results if r["status"] in ("found", "partial")]
    rate = len(success) / len(results)
    print(f"\nTaxa de sucesso H2: {rate:.0%} ({len(success)}/{len(results)})")
    assert rate >= 0.70, f"H2 não atingido: {rate:.0%} < 70%"


# ─── orchestrator — Passo 1c (domain_id) ──────────────────────────────────────

class TestOrchestrateDomainId:

    def _make_whois_privacy(self, domain="exemplo.com") -> dict:
        return {
            "domain": domain, "registrant": "WhoisGuard Protected",
            "responsible": None, "contacts": [], "registrant_email": None,
            "registrar": "Namecheap", "creation_date": "2021-01-01",
            "expiration_date": "2025-01-01", "name_servers": ["ns1.namecheap.com"],
            "document": None,
            "registrobr_url": f"https://registro.br/tecnologia/ferramentas/whois?search={domain}",
            "status": "found", "requires_manual_review": False, "message": None,
        }

    def _make_whois_not_found(self, domain="exemplo.com") -> dict:
        return {
            "domain": domain, "registrant": None, "responsible": None, "contacts": [],
            "registrant_email": None, "registrar": None, "creation_date": None,
            "expiration_date": None, "name_servers": [], "document": None,
            "registrobr_url": f"https://registro.br/tecnologia/ferramentas/whois?search={domain}",
            "status": "not_found", "requires_manual_review": True,
            "message": "WHOIS sem dados de registrante — validar manualmente",
        }

    def _make_cnpj_not_found(self) -> dict:
        return {
            "cnpj": None, "razao_social": None, "nome_fantasia": None,
            "situacao": None, "atividade_principal": None, "logradouro": None,
            "socios": [], "status": "not_found", "requires_manual_review": True,
            "message": "CNPJ não encontrado — validar manualmente",
        }

    async def test_domain_id_called_for_com_with_privacy_proxy(self):
        """Para .com com privacy proxy no WHOIS, aciona identify_domain_operator."""
        from src.lookup.orchestrator import lookup_domain

        domain_id_result = {
            "org": "Empresa Via crt.sh Ltda", "source": "crt.sh",
            "status": "found", "requires_manual_review": False, "message": None,
        }

        with patch("src.lookup.orchestrator.lookup_whois", return_value=self._make_whois_privacy()), \
             patch("src.lookup.orchestrator.lookup_rdap", return_value={"status": "not_found"}), \
             patch("src.lookup.orchestrator.identify_domain_operator", new_callable=AsyncMock,
                   return_value=domain_id_result) as mock_domain_id, \
             patch("src.lookup.orchestrator.lookup_cnpj", new_callable=AsyncMock,
                   return_value=self._make_cnpj_not_found()), \
             patch("src.lookup.orchestrator.extract_cnpj_from_text", new_callable=AsyncMock,
                   return_value=None):

            result = await lookup_domain("exemplo.com")

        mock_domain_id.assert_called_once_with("exemplo.com")
        assert result["domain_id"]["org"] == "Empresa Via crt.sh Ltda"
        assert result["domain_id"]["source"] == "crt.sh"

    async def test_domain_id_not_called_for_br_domain(self):
        """Para .com.br, Passo 1c nunca é acionado."""
        from src.lookup.orchestrator import lookup_domain

        whois_br = {
            "domain": "exemplo.com.br", "registrant": "Empresa BR Ltda",
            "responsible": None, "contacts": [], "registrant_email": None,
            "registrar": "Registro.br", "creation_date": "2021-01-01",
            "expiration_date": "2025-01-01", "name_servers": ["ns1.exemplo.com.br"],
            "document": "12.345.678/0001-99",
            "registrobr_url": "https://registro.br/...",
            "status": "found", "requires_manual_review": False, "message": None,
        }
        cnpj_found = {
            "cnpj": "12345678000199", "razao_social": "Empresa BR Ltda",
            "nome_fantasia": None, "situacao": "ATIVA", "atividade_principal": None,
            "logradouro": None, "socios": [], "status": "found",
            "requires_manual_review": False, "message": None,
        }

        with patch("src.lookup.orchestrator.lookup_whois", return_value=whois_br), \
             patch("src.lookup.orchestrator.identify_domain_operator") as mock_domain_id, \
             patch("src.lookup.orchestrator.lookup_cnpj", new_callable=AsyncMock,
                   return_value=cnpj_found), \
             patch("src.lookup.orchestrator.extract_cnpj_from_text", new_callable=AsyncMock,
                   return_value="12.345.678/0001-99"):

            result = await lookup_domain("exemplo.com.br")

        mock_domain_id.assert_not_called()

    async def test_domain_id_not_called_when_whois_has_real_registrant(self):
        """Para .com com registrante real no WHOIS, Passo 1c não é acionado."""
        from src.lookup.orchestrator import lookup_domain

        whois_com_real = {
            "domain": "exemplo.com", "registrant": "Real Company Inc",
            "responsible": None, "contacts": [], "registrant_email": "admin@real.com",
            "registrar": "GoDaddy", "creation_date": "2019-03-01",
            "expiration_date": "2026-03-01", "name_servers": ["ns1.godaddy.com"],
            "document": None, "registrobr_url": "https://registro.br/...",
            "status": "found", "requires_manual_review": False, "message": None,
        }

        with patch("src.lookup.orchestrator.lookup_whois", return_value=whois_com_real), \
             patch("src.lookup.orchestrator.identify_domain_operator") as mock_domain_id, \
             patch("src.lookup.orchestrator.lookup_cnpj", new_callable=AsyncMock,
                   return_value=self._make_cnpj_not_found()), \
             patch("src.lookup.orchestrator.extract_cnpj_from_text", new_callable=AsyncMock,
                   return_value=None):

            result = await lookup_domain("exemplo.com")

        mock_domain_id.assert_not_called()

    async def test_domain_id_result_added_to_return_dict(self):
        """Resultado do domain_id aparece na chave 'domain_id' do retorno."""
        from src.lookup.orchestrator import lookup_domain

        domain_id_pending = {
            "org": None, "source": "pending", "status": "pending",
            "requires_manual_review": True,
            "message": "Operador não identificado automaticamente",
        }

        with patch("src.lookup.orchestrator.lookup_whois", return_value=self._make_whois_not_found()), \
             patch("src.lookup.orchestrator.lookup_rdap", return_value={"status": "not_found"}), \
             patch("src.lookup.orchestrator.identify_domain_operator", new_callable=AsyncMock,
                   return_value=domain_id_pending), \
             patch("src.lookup.orchestrator.lookup_cnpj", new_callable=AsyncMock,
                   return_value=self._make_cnpj_not_found()), \
             patch("src.lookup.orchestrator.extract_cnpj_from_text", new_callable=AsyncMock,
                   return_value=None):

            result = await lookup_domain("exemplo.com")

        assert "domain_id" in result
        assert result["domain_id"]["status"] == "pending"
        assert result["domain_id"]["requires_manual_review"] is True
