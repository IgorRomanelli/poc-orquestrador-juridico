"""
Testes para full_search.run_full_search — orquestrador das 4 fontes de busca.

Cobre:
1. Resultado final contém as chaves obrigatórias (image_url, page_url, source, confidence)
2. Deduplicação por page_url mantendo o item de maior confidence
3. S3 cleanup (delete_object) é chamado mesmo quando há exceção (finally)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

# ─── fixtures ─────────────────────────────────────────────────────────────────

_ORCHESTRATOR_RESULT = {
    "results": [
        {
            "image_url": "https://img.example.com/a.jpg",
            "page_url": "https://example.com/page-a",
            "source": "facecheck",
            "confidence": 0.9,
        },
        {
            "image_url": "https://img.example.com/b.jpg",
            "page_url": "https://example.com/page-b",
            "source": "googlevision",
            "confidence": 0.7,
        },
    ],
    "status": "found",
}

_SERPER_RESULT = {
    "results": [
        {
            "image_url": "https://img.serper.com/x.jpg",
            "page_url": "https://example.com/page-b",  # duplicate — lower confidence
            "source": "serper",
            "confidence": None,
        },
        {
            "image_url": "https://img.serper.com/y.jpg",
            "page_url": "https://serper.com/page-c",
            "source": "serper",
            "confidence": None,
        },
    ],
    "status": "found",
}

_SEARCHAPI_RESULT = {
    "results": [
        {
            "image_url": "https://img.searchapi.com/z.jpg",
            "page_url": "https://searchapi.com/page-d",
            "source": "searchapi",
            "confidence": None,
        },
    ],
    "status": "found",
}


def _make_patches(
    orchestrator_result=None,
    serper_result=None,
    searchapi_result=None,
    presigned_url="https://s3.example.com/temp.jpg",
    s3_key="temp-search/uuid.jpg",
):
    return {
        "upload": patch(
            "src.search.full_search.s3_temp_client.upload_and_get_url",
            return_value=(presigned_url, s3_key),
        ),
        "delete": patch(
            "src.search.full_search.s3_temp_client.delete_object",
        ),
        "orchestrator": patch(
            "src.search.full_search.search_image",
            new=AsyncMock(return_value=orchestrator_result or _ORCHESTRATOR_RESULT),
        ),
        "serper": patch(
            "src.search.full_search.serper_client.search_by_image_url",
            new=AsyncMock(return_value=serper_result or _SERPER_RESULT),
        ),
        "searchapi": patch(
            "src.search.full_search.searchapi_client.search_by_image_url",
            new=AsyncMock(return_value=searchapi_result or _SEARCHAPI_RESULT),
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Testes
# ══════════════════════════════════════════════════════════════════════════════


class TestRunFullSearch:

    async def test_results_have_required_keys(self):
        """Todos os itens retornados devem ter image_url, page_url, source, confidence."""
        from src.search.full_search import run_full_search

        patches = _make_patches()
        with patches["upload"], patches["delete"], patches["orchestrator"], \
             patches["serper"], patches["searchapi"]:
            results = await run_full_search("photo.jpg", b"image-bytes")

        assert isinstance(results, list)
        assert len(results) > 0
        required_keys = {"image_url", "page_url", "source", "confidence"}
        for item in results:
            assert required_keys.issubset(item.keys()), (
                f"Item faltando chaves obrigatórias: {required_keys - item.keys()}"
            )

    async def test_deduplication_keeps_highest_confidence(self):
        """
        page_url duplicado: manter o item com maior confidence.
        page-b aparece em orchestrator (confidence=0.7) e serper (confidence=None).
        O item do orchestrator (0.7) deve ser mantido.
        """
        from src.search.full_search import run_full_search

        patches = _make_patches()
        with patches["upload"], patches["delete"], patches["orchestrator"], \
             patches["serper"], patches["searchapi"]:
            results = await run_full_search("photo.jpg", b"image-bytes")

        page_b_items = [r for r in results if r["page_url"] == "https://example.com/page-b"]
        assert len(page_b_items) == 1, "page-b não foi deduplicado corretamente"
        assert page_b_items[0]["confidence"] == 0.7, (
            f"Esperado confidence=0.7, obtido {page_b_items[0]['confidence']}"
        )

    async def test_deduplication_none_vs_float_keeps_float(self):
        """
        Quando um duplicado tem confidence=None e outro tem float, manter o float.
        """
        from src.search.full_search import run_full_search

        # serper traz page-a com confidence=None, orchestrator já tem page-a com 0.9
        serper_with_dup = {
            "results": [
                {
                    "image_url": "https://img.serper.com/dup.jpg",
                    "page_url": "https://example.com/page-a",  # dup de orchestrator (0.9)
                    "source": "serper",
                    "confidence": None,
                },
            ],
            "status": "found",
        }
        patches = _make_patches(serper_result=serper_with_dup)
        with patches["upload"], patches["delete"], patches["orchestrator"], \
             patches["serper"], patches["searchapi"]:
            results = await run_full_search("photo.jpg", b"image-bytes")

        page_a_items = [r for r in results if r["page_url"] == "https://example.com/page-a"]
        assert len(page_a_items) == 1
        assert page_a_items[0]["confidence"] == 0.9

    async def test_s3_cleanup_called_on_success(self):
        """delete_object deve ser chamado com o s3_key correto após busca bem-sucedida."""
        from src.search.full_search import run_full_search

        patches = _make_patches(s3_key="temp-search/my-key.jpg")
        with patches["upload"], patches["delete"] as mock_delete, \
             patches["orchestrator"], patches["serper"], patches["searchapi"]:
            await run_full_search("photo.jpg", b"image-bytes")

        mock_delete.assert_called_once_with("temp-search/my-key.jpg")

    async def test_s3_cleanup_called_on_search_failure(self):
        """delete_object deve ser chamado mesmo quando a busca falha (finally block)."""
        from src.search.full_search import run_full_search

        patches = _make_patches(s3_key="temp-search/my-key.jpg")
        failing_orchestrator = patch(
            "src.search.full_search.search_image",
            new=AsyncMock(side_effect=RuntimeError("API down")),
        )
        with patches["upload"], patches["delete"] as mock_delete, \
             failing_orchestrator, patches["serper"], patches["searchapi"]:
            with pytest.raises(RuntimeError):
                await run_full_search("photo.jpg", b"image-bytes")

        mock_delete.assert_called_once_with("temp-search/my-key.jpg")

    async def test_all_unique_results_included(self):
        """Resultados únicos de todas as 3 fontes devem aparecer na lista final."""
        from src.search.full_search import run_full_search

        patches = _make_patches()
        with patches["upload"], patches["delete"], patches["orchestrator"], \
             patches["serper"], patches["searchapi"]:
            results = await run_full_search("photo.jpg", b"image-bytes")

        page_urls = {r["page_url"] for r in results}
        assert "https://example.com/page-a" in page_urls
        assert "https://example.com/page-b" in page_urls
        assert "https://serper.com/page-c" in page_urls
        assert "https://searchapi.com/page-d" in page_urls
