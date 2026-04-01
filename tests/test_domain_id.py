"""
Testes para domain_id_client — pipeline crt.sh → Netlas.io.
Todos os testes são unitários (sem I/O real).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


class TestLookupByCerts:

    async def test_found_returns_org_from_subject_o(self):
        """crt.sh retorna cert com subject_o — extrai org e retorna status found."""
        from src.lookup.domain_id_client import lookup_by_certs

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [
            {"subject_o": "Empresa Exemplo Ltda", "entry_timestamp": "2024-06-01"},
            {"subject_o": "Let's Encrypt", "entry_timestamp": "2023-01-01"},
        ]

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_certs("exemplo.com")

        assert result["status"] == "found"
        assert result["org"] == "Empresa Exemplo Ltda"
        assert result["source"] == "crt.sh"
        assert result["requires_manual_review"] is False

    async def test_filters_letsencrypt_and_known_cas(self):
        """Filtra CAs conhecidas — não são operadores."""
        from src.lookup.domain_id_client import lookup_by_certs

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [
            {"subject_o": "Let's Encrypt", "entry_timestamp": "2024-06-01"},
            {"subject_o": "Comodo CA Limited", "entry_timestamp": "2023-06-01"},
            {"subject_o": "Empresa Real Ltda", "entry_timestamp": "2022-06-01"},
        ]

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_certs("exemplo.com")

        assert result["status"] == "found"
        assert result["org"] == "Empresa Real Ltda"

    async def test_empty_json_returns_not_found(self):
        """crt.sh retorna lista vazia — not_found."""
        from src.lookup.domain_id_client import lookup_by_certs

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = []

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_certs("exemplo.com")

        assert result["status"] == "not_found"
        assert result["org"] is None
        assert result["source"] == "crt.sh"
        assert result["requires_manual_review"] is True

    async def test_http_error_returns_error(self):
        """Erro HTTP (status != 200) retorna status error."""
        from src.lookup.domain_id_client import lookup_by_certs

        fake_response = MagicMock()
        fake_response.status_code = 503

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_certs("exemplo.com")

        assert result["status"] == "error"
        assert result["org"] is None
        assert result["requires_manual_review"] is True

    async def test_network_exception_returns_error(self):
        """Exceção de rede retorna status error com mensagem descritiva."""
        from src.lookup.domain_id_client import lookup_by_certs

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = Exception("Connection refused")

            result = await lookup_by_certs("exemplo.com")

        assert result["status"] == "error"
        assert result["org"] is None
        assert "crt.sh" in result["message"]
        assert result["requires_manual_review"] is True


class TestLookupByNetlas:

    async def test_found_returns_org_from_registrant_organization(self):
        """Netlas retorna whois histórico com registrant_organization."""
        from src.lookup.domain_id_client import lookup_by_netlas

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "count": 1,
            "items": [
                {"data": {"registrant_organization": "Empresa Via Netlas Ltda", "registrant_name": "Joao Silva"}}
            ],
        }

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_netlas("exemplo.com", api_key="test-key")

        assert result["status"] == "found"
        assert result["org"] == "Empresa Via Netlas Ltda"
        assert result["source"] == "netlas"
        assert result["requires_manual_review"] is False

    async def test_falls_back_to_registrant_name_when_no_org(self):
        """Quando registrant_organization ausente, usa registrant_name."""
        from src.lookup.domain_id_client import lookup_by_netlas

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "count": 1,
            "items": [{"data": {"registrant_organization": None, "registrant_name": "Joao Silva"}}],
        }

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_netlas("exemplo.com", api_key="test-key")

        assert result["status"] == "found"
        assert result["org"] == "Joao Silva"

    async def test_empty_items_returns_not_found(self):
        """Netlas sem resultados retorna not_found."""
        from src.lookup.domain_id_client import lookup_by_netlas

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"count": 0, "items": []}

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_netlas("exemplo.com", api_key="test-key")

        assert result["status"] == "not_found"
        assert result["org"] is None
        assert result["source"] == "netlas"
        assert result["requires_manual_review"] is True

    async def test_http_401_returns_error(self):
        """API key inválida (401) retorna error."""
        from src.lookup.domain_id_client import lookup_by_netlas

        fake_response = MagicMock()
        fake_response.status_code = 401

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = fake_response

            result = await lookup_by_netlas("exemplo.com", api_key="invalid-key")

        assert result["status"] == "error"
        assert result["org"] is None
        assert result["requires_manual_review"] is True

    async def test_network_exception_returns_error(self):
        """Exceção de rede retorna error com mensagem descritiva."""
        from src.lookup.domain_id_client import lookup_by_netlas

        with patch("src.lookup.domain_id_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = Exception("timeout")

            result = await lookup_by_netlas("exemplo.com", api_key="test-key")

        assert result["status"] == "error"
        assert "netlas" in result["message"].lower()


class TestIdentifyDomainOperator:

    async def test_returns_crtsh_result_when_found(self):
        """crt.sh encontra org — não chama Netlas."""
        from src.lookup.domain_id_client import identify_domain_operator

        crt_result = {"status": "found", "org": "Empresa crt.sh", "source": "crt.sh",
                      "requires_manual_review": False, "message": None}

        with patch("src.lookup.domain_id_client.lookup_by_certs", return_value=crt_result) as mock_crt, \
             patch("src.lookup.domain_id_client.lookup_by_netlas") as mock_netlas:

            result = await identify_domain_operator("exemplo.com")

        assert result["org"] == "Empresa crt.sh"
        assert result["source"] == "crt.sh"
        mock_netlas.assert_not_called()

    async def test_falls_through_to_netlas_when_crtsh_not_found(self):
        """crt.sh not_found → aciona Netlas."""
        from src.lookup.domain_id_client import identify_domain_operator

        crt_result = {"status": "not_found", "org": None, "source": "crt.sh",
                      "requires_manual_review": True, "message": "sem certs"}
        netlas_result = {"status": "found", "org": "Empresa Netlas", "source": "netlas",
                         "requires_manual_review": False, "message": None}

        with patch("src.lookup.domain_id_client.lookup_by_certs", return_value=crt_result), \
             patch("src.lookup.domain_id_client.lookup_by_netlas", return_value=netlas_result), \
             patch("src.lookup.domain_id_client.os.environ.get", return_value="test-key"):

            result = await identify_domain_operator("exemplo.com")

        assert result["org"] == "Empresa Netlas"
        assert result["source"] == "netlas"

    async def test_falls_through_to_netlas_when_crtsh_error(self):
        """crt.sh error → tenta Netlas mesmo assim."""
        from src.lookup.domain_id_client import identify_domain_operator

        crt_result = {"status": "error", "org": None, "source": "crt.sh",
                      "requires_manual_review": True, "message": "timeout"}
        netlas_result = {"status": "found", "org": "Empresa Netlas", "source": "netlas",
                         "requires_manual_review": False, "message": None}

        with patch("src.lookup.domain_id_client.lookup_by_certs", return_value=crt_result), \
             patch("src.lookup.domain_id_client.lookup_by_netlas", return_value=netlas_result), \
             patch("src.lookup.domain_id_client.os.environ.get", return_value="test-key"):

            result = await identify_domain_operator("exemplo.com")

        assert result["org"] == "Empresa Netlas"

    async def test_skips_netlas_when_no_api_key(self):
        """Sem NETLAS_API_KEY — retorna pending sem tentar Netlas."""
        from src.lookup.domain_id_client import identify_domain_operator

        crt_result = {"status": "not_found", "org": None, "source": "crt.sh",
                      "requires_manual_review": True, "message": "sem certs"}

        with patch("src.lookup.domain_id_client.lookup_by_certs", return_value=crt_result), \
             patch("src.lookup.domain_id_client.lookup_by_netlas") as mock_netlas, \
             patch("src.lookup.domain_id_client.os.environ.get", return_value=None):

            result = await identify_domain_operator("exemplo.com")

        mock_netlas.assert_not_called()
        assert result["status"] == "pending"
        assert result["org"] is None
        assert result["requires_manual_review"] is True

    async def test_returns_pending_when_both_fail(self):
        """crt.sh + Netlas ambos falham → pending."""
        from src.lookup.domain_id_client import identify_domain_operator

        not_found = {"status": "not_found", "org": None, "source": "crt.sh",
                     "requires_manual_review": True, "message": "sem dados"}

        with patch("src.lookup.domain_id_client.lookup_by_certs", return_value=not_found), \
             patch("src.lookup.domain_id_client.lookup_by_netlas", return_value={
                 "status": "not_found", "org": None, "source": "netlas",
                 "requires_manual_review": True, "message": "sem dados"
             }), \
             patch("src.lookup.domain_id_client.os.environ.get", return_value="test-key"):

            result = await identify_domain_operator("exemplo.com")

        assert result["status"] == "pending"
        assert result["org"] is None
        assert result["source"] == "pending"
        assert result["requires_manual_review"] is True
        assert result["message"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# Seção 2 — Testes de integração (I/O real, skipados por padrão)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestDomainIdIntegration:
    """
    Testes reais contra crt.sh e Netlas.io.
    Rodar com: pytest -m integration tests/test_domain_id.py -v

    Requer NETLAS_API_KEY no ambiente para os testes do Netlas.
    """

    async def test_crtsh_real_domain(self):
        """crt.sh retorna resultado para domínio real conhecido."""
        from src.lookup.domain_id_client import lookup_by_certs

        result = await lookup_by_certs("google.com")
        assert result["status"] in ("found", "not_found")
        assert "source" in result
        print(f"\ncrt.sh google.com → org={result['org']} status={result['status']}")

    async def test_identify_operator_real_domain(self):
        """Pipeline completo para domínio .com."""
        from src.lookup.domain_id_client import identify_domain_operator

        result = await identify_domain_operator("namecheap.com")
        assert result["status"] in ("found", "not_found", "pending")
        assert "org" in result
        assert "source" in result
        print(f"\nidentify_operator namecheap.com → org={result['org']} source={result['source']}")
