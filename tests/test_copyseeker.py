"""
Testes unitários para copyseeker_client.
Todos os testes mockam o HTTP — sem chamadas reais à API.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


class TestCopyseekerClient:

    async def test_missing_api_key_returns_error(self):
        """Sem COPYSEEKER_API_KEY configurada, retorna error sem HTTP."""
        with patch("src.search.copyseeker_client._API_KEY", ""):
            from src.search import copyseeker_client
            import importlib
            importlib.reload(copyseeker_client)
            result = await copyseeker_client.search_by_image_url("https://s3.example.com/image.jpg")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "COPYSEEKER_API_KEY" in result["message"]
        assert result["results"] == []

    async def test_found_returns_results_with_required_keys(self):
        """Resposta com Pages retorna status found e lista com chaves obrigatórias."""
        fake_response_json = {
            "Pages": [
                {"Url": "https://example.com/page1", "MatchingImages": ["https://img.example.com/1.jpg"], "Rank": 0.9},
                {"Url": "https://other.com/page2", "MatchingImages": [], "Rank": 0.8},
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_response_json
        mock_response.raise_for_status = MagicMock()

        with (
            patch("src.search.copyseeker_client._API_KEY", "test-key"),
            patch("src.search.copyseeker_client.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from src.search import copyseeker_client
            result = await copyseeker_client.search_by_image_url("https://s3.example.com/image.jpg")

        assert result["status"] == "found"
        assert result["requires_manual_review"] is False
        assert len(result["results"]) == 2

        item = result["results"][0]
        for key in ("page_url", "domain", "source", "confidence", "source_confidence", "preview_thumbnail", "image_url"):
            assert key in item, f"Chave ausente: {key}"

        assert item["source"] == "copyseeker"
        assert item["confidence"] is None
        assert item["source_confidence"] == 0.70
        assert item["page_url"] == "https://example.com/page1"
        assert item["preview_thumbnail"] == "https://img.example.com/1.jpg"

    async def test_empty_pages_returns_not_found(self):
        """Pages vazio retorna not_found."""
        fake_response_json = {"Pages": []}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_response_json
        mock_response.raise_for_status = MagicMock()

        with (
            patch("src.search.copyseeker_client._API_KEY", "test-key"),
            patch("src.search.copyseeker_client.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from src.search import copyseeker_client
            result = await copyseeker_client.search_by_image_url("https://s3.example.com/image.jpg")

        assert result["status"] == "not_found"
        assert result["results"] == []

    async def test_network_exception_returns_error(self):
        """Exceção de rede retorna error com requires_manual_review=True."""
        with (
            patch("src.search.copyseeker_client._API_KEY", "test-key"),
            patch("src.search.copyseeker_client.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            from src.search import copyseeker_client
            result = await copyseeker_client.search_by_image_url("https://s3.example.com/image.jpg")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "CopySeeker" in result["message"]

    async def test_domain_extracted_from_page_url(self):
        """domain é extraído corretamente da Url, sem 'www.'."""
        fake_response_json = {
            "Pages": [{"Url": "https://www.site.com.br/foto", "MatchingImages": [], "Rank": 0.8}]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_response_json
        mock_response.raise_for_status = MagicMock()

        with (
            patch("src.search.copyseeker_client._API_KEY", "test-key"),
            patch("src.search.copyseeker_client.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from src.search import copyseeker_client
            result = await copyseeker_client.search_by_image_url("https://s3.example.com/image.jpg")

        assert result["results"][0]["domain"] == "site.com.br"
