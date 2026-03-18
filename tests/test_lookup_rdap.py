"""
Testes unitários — RDAP client e detecção de privacy proxy.
"""

import pytest
from unittest.mock import MagicMock, patch


# ─── TestRdapClient ────────────────────────────────────────────────────────────

class TestRdapClient:

    def test_returns_found_for_valid_domain(self):
        """lookup_rdap deve retornar status 'found' quando RDAP responde com dados."""
        rdap_payload = {
            "ldhName": "example.com",
            "entities": [
                {
                    "roles": ["registrant"],
                    "vcardArray": [
                        "vcard",
                        [
                            ["version", {}, "text", "4.0"],
                            ["fn", {}, "text", "Example Registrant"],
                        ],
                    ],
                }
            ],
            "events": [
                {"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"},
                {"eventAction": "expiration", "eventDate": "2026-01-01T00:00:00Z"},
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = rdap_payload

        with patch("httpx.get", return_value=mock_response):
            from src.lookup.rdap_client import lookup_rdap
            result = lookup_rdap("example.com")

        assert result["status"] == "found"
        assert result["registrant"] == "Example Registrant"
        assert "2020" in result.get("created", "")

    def test_returns_not_found_on_404(self):
        """lookup_rdap deve retornar status 'not_found' quando RDAP retorna 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.get", return_value=mock_response):
            from src.lookup.rdap_client import lookup_rdap
            result = lookup_rdap("nonexistent-domain-xyz.com")

        assert result["status"] == "not_found"

    def test_returns_error_on_timeout(self):
        """lookup_rdap deve retornar status 'error' quando ocorre timeout."""
        import httpx

        with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
            from src.lookup.rdap_client import lookup_rdap
            result = lookup_rdap("example.com")

        assert result["status"] == "error"


# ─── TestPrivacyProxyDetection ─────────────────────────────────────────────────

class TestPrivacyProxyDetection:

    def _is_privacy_proxy(self, value):
        from src.lookup.whois_client import _is_privacy_proxy
        return _is_privacy_proxy(value)

    def test_domains_by_proxy_detected(self):
        assert self._is_privacy_proxy("Domains By Proxy LLC") is True

    def test_whoisguard_detected(self):
        assert self._is_privacy_proxy("WhoisGuard, Inc.") is True

    def test_privacyprotect_detected(self):
        assert self._is_privacy_proxy("PrivacyProtect.org") is True

    def test_real_registrant_not_detected(self):
        assert self._is_privacy_proxy("Empresa Exemplo Ltda") is False

    def test_none_not_detected(self):
        assert self._is_privacy_proxy(None) is False
