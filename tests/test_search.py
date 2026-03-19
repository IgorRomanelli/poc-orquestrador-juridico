"""
Testes para o módulo de busca de imagem (Hipótese 1).

Seção 1 — Testes unitários (sem I/O real, rodam sempre)
Seção 2 — Testes de integração (requerem imagens reais, skipados por padrão)

Critério de sucesso H1: recall ≥ 70% dos casos (definido em specs/poc-tecnica.md).
"""

from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

pytestmark = pytest.mark.asyncio


# ══════════════════════════════════════════════════════════════════════════════
# Seção 1 — Testes unitários (sem I/O)
# ══════════════════════════════════════════════════════════════════════════════

# ─── facecheck_client ─────────────────────────────────────────────────────────

class TestFacecheckClient:

    def _make_upload_response(self, id_search="abc123"):
        r = MagicMock()
        r.json.return_value = {"error": None, "code": "ok", "id_search": id_search, "message": "uploaded"}
        return r

    def _make_search_response(self, items=None, progress=100, output_ready=True):
        r = MagicMock()
        output = {"items": items or []} if output_ready else None
        r.json.return_value = {
            "error": None,
            "code": "ok",
            "message": "done",
            "progress": progress,
            "output": output,
        }
        return r

    async def test_found_returns_required_keys(self):
        """Resultado found contém todas as chaves obrigatórias."""
        from src.search.facecheck_client import search_by_face

        fake_items = [
            {"score": 87, "url": "https://example.com/page", "base64": "abc123", "guid": "g1", "index": 0}
        ]

        with (
            patch("src.search.facecheck_client._API_TOKEN", "fake-token"),
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=[
                self._make_upload_response(),
                self._make_search_response(items=fake_items),
            ])
            mock_cls.return_value = mock_client

            result = await search_by_face("foto.jpg")

        assert result["status"] == "found"
        assert result["requires_manual_review"] is False
        assert len(result["results"]) == 1
        item = result["results"][0]
        for key in ("image_url", "page_url", "domain", "source", "confidence", "preview_thumbnail"):
            assert key in item, f"Chave ausente: {key}"
        assert item["source"] == "facecheck"
        assert item["domain"] == "example.com"

    async def test_upload_error_returns_error(self):
        """Erro no upload retorna status error."""
        from src.search.facecheck_client import search_by_face

        error_response = MagicMock()
        error_response.json.return_value = {"error": "Token inválido", "code": "AUTH_ERROR"}

        with (
            patch("src.search.facecheck_client._API_TOKEN", "bad-token"),
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=error_response)
            mock_cls.return_value = mock_client

            result = await search_by_face("foto.jpg")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True
        assert "Token inválido" in result["message"]

    async def test_polling_timeout_returns_error(self):
        """Polling que nunca resolve retorna error após timeout."""
        from src.search.facecheck_client import search_by_face

        in_progress = MagicMock()
        in_progress.json.return_value = {
            "error": None, "code": "ok", "message": "searching",
            "progress": 50, "output": None,
        }

        with (
            patch("src.search.facecheck_client._API_TOKEN", "fake-token"),
            patch("src.search.facecheck_client._MAX_POLLING_SECONDS", 0),  # timeout imediato
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=[
                self._make_upload_response(),
                in_progress,
            ])
            mock_cls.return_value = mock_client

            result = await search_by_face("foto.jpg")

        assert result["status"] == "error"
        assert "timeout" in result["message"].lower()

    async def test_normalize_items_maps_score_to_confidence(self):
        """score 87 → confidence 0.87."""
        from src.search.facecheck_client import _normalize_items

        items = [{"score": 87, "url": "https://example.com/page", "base64": "b64", "guid": "g1", "index": 0}]
        result = _normalize_items(items)

        assert len(result) == 1
        assert result[0]["confidence"] == 0.87

    async def test_missing_api_token_returns_error(self):
        """Sem token configurado retorna error imediatamente."""
        from src.search.facecheck_client import search_by_face

        with patch("src.search.facecheck_client._API_TOKEN", ""):
            result = await search_by_face("foto.jpg")

        assert result["status"] == "error"
        assert "FACECHECK_API_KEY" in result["message"]


# ─── google_vision_client ─────────────────────────────────────────────────────

class TestGoogleVisionClient:

    def _make_vision_response(self, pages=None, similar=None):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "responses": [{
                "webDetection": {
                    "pagesWithMatchingImages": pages or [],
                    "visuallySimilarImages": similar or [],
                    "webEntities": [],
                    "bestGuessLabels": [],
                }
            }]
        }
        return r

    async def test_found_returns_required_keys(self):
        """Resultado found contém todas as chaves obrigatórias."""
        from src.search.google_vision_client import search_by_image

        pages = [
            {
                "url": "https://example.com/page",
                "pageTitle": "Example",
                "fullMatchingImages": [{"url": "https://example.com/img.jpg"}],
                "partialMatchingImages": [],
            }
        ]

        with (
            patch("src.search.google_vision_client._API_KEY", "fake-key"),
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=self._make_vision_response(pages=pages))
            mock_cls.return_value = mock_client

            result = await search_by_image("foto.jpg")

        assert result["status"] == "found"
        assert result["requires_manual_review"] is False
        assert len(result["results"]) == 1
        item = result["results"][0]
        for key in ("image_url", "page_url", "domain", "source", "confidence", "preview_thumbnail"):
            assert key in item, f"Chave ausente: {key}"
        assert item["source"] == "google_vision"
        assert item["image_url"] == "https://example.com/img.jpg"

    async def test_http_error_returns_error(self):
        """HTTP 403 retorna status error."""
        from src.search.google_vision_client import search_by_image

        fake_response = MagicMock()
        fake_response.status_code = 403

        with (
            patch("src.search.google_vision_client._API_KEY", "bad-key"),
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=fake_response)
            mock_cls.return_value = mock_client

            result = await search_by_image("foto.jpg")

        assert result["status"] == "error"
        assert "403" in result["message"]

    async def test_empty_web_detection_returns_not_found(self):
        """WebDetection vazio retorna not_found."""
        from src.search.google_vision_client import search_by_image

        with (
            patch("src.search.google_vision_client._API_KEY", "fake-key"),
            patch("httpx.AsyncClient") as mock_cls,
            patch("builtins.open", mock_open(read_data=b"img")),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=self._make_vision_response())
            mock_cls.return_value = mock_client

            result = await search_by_image("foto.jpg")

        assert result["status"] == "not_found"

    async def test_normalize_extracts_domain(self):
        """page_url com www → domain sem www."""
        from src.search.google_vision_client import _normalize_response

        web_detection = {
            "pagesWithMatchingImages": [
                {
                    "url": "https://www.example.com/page",
                    "fullMatchingImages": [{"url": "https://www.example.com/img.jpg"}],
                    "partialMatchingImages": [],
                }
            ],
            "visuallySimilarImages": [],
        }

        results = _normalize_response(web_detection)

        assert len(results) == 1
        assert results[0]["domain"] == "example.com"

    async def test_missing_api_key_returns_error(self):
        """Sem chave configurada retorna error imediatamente."""
        from src.search.google_vision_client import search_by_image

        with patch("src.search.google_vision_client._API_KEY", ""):
            result = await search_by_image("foto.jpg")

        assert result["status"] == "error"
        assert "GOOGLE_CLOUD_API_KEY" in result["message"]


# ─── aggregator ───────────────────────────────────────────────────────────────

class TestAggregator:

    def _item(self, page_url, source="facecheck", confidence=0.9):
        from urllib.parse import urlparse
        domain = urlparse(page_url).netloc.removeprefix("www.")
        return {
            "image_url": None,
            "page_url": page_url,
            "domain": domain,
            "source": source,
            "confidence": confidence,
            "preview_thumbnail": None,
        }

    def _found(self, items):
        return {"results": items, "status": "found", "requires_manual_review": False, "message": None}

    def _error(self, msg="erro"):
        return {"results": [], "status": "error", "requires_manual_review": True, "message": msg}

    def _not_found(self):
        return {"results": [], "status": "not_found", "requires_manual_review": False, "message": None}

    async def test_deduplicates_by_page_url(self):
        """Mesmo page_url de fontes diferentes não duplica."""
        from src.search.aggregator import aggregate

        item_fc = self._item("https://example.com/page", source="facecheck", confidence=0.9)
        item_gv = self._item("https://example.com/page", source="google_vision", confidence=None)

        result = aggregate(self._found([item_fc]), self._found([item_gv]))

        assert result["total_raw"] == 2
        assert result["total_deduplicated"] == 1

    async def test_keeps_both_sources_for_same_domain_different_url(self):
        """Mesmo domínio, page_url diferente → mantém os dois."""
        from src.search.aggregator import aggregate

        item_fc = self._item("https://example.com/page1", source="facecheck")
        item_gv = self._item("https://example.com/page2", source="google_vision")

        result = aggregate(self._found([item_fc]), self._found([item_gv]))

        assert result["total_deduplicated"] == 2
        assert len(result["domains"]) == 1  # mesmo domínio

    async def test_sorts_by_confidence_desc(self):
        """Resultados ordenados por confidence desc; None vai para o final."""
        from src.search.aggregator import aggregate

        items_fc = [self._item("https://a.com/p", confidence=0.5)]
        items_gv = [
            self._item("https://b.com/p", source="google_vision", confidence=None),
            self._item("https://c.com/p", source="google_vision", confidence=0.9),
        ]

        result = aggregate(self._found(items_fc), self._found(items_gv))

        confidences = [r["confidence"] for r in result["results"]]
        assert confidences == [0.9, 0.5, None]

    async def test_extracts_unique_domains(self):
        """Lista de domains sem repetição, preservando ordem de aparição."""
        from src.search.aggregator import aggregate

        items_fc = [
            self._item("https://site-a.com/p1"),
            self._item("https://site-b.com/p1"),
        ]
        items_gv = [
            self._item("https://site-a.com/p2", source="google_vision"),
        ]

        result = aggregate(self._found(items_fc), self._found(items_gv))

        assert result["domains"] == ["site-a.com", "site-b.com"]

    async def test_status_partial_when_one_error_one_found(self):
        """Uma fonte com error e outra com found → status partial."""
        from src.search.aggregator import aggregate

        result = aggregate(
            self._found([self._item("https://example.com/p")]),
            self._error("timeout"),
        )

        assert result["status"] == "partial"

    async def test_status_not_found_when_both_empty(self):
        """Ambas sem resultado → not_found."""
        from src.search.aggregator import aggregate

        result = aggregate(self._not_found(), self._not_found())

        assert result["status"] == "not_found"
        assert result["total_deduplicated"] == 0

    def test_aggregate_three_sources(self):
        """aggregate aceita três fontes e une todos os resultados."""
        from src.search.aggregator import aggregate

        fc = {"status": "found", "results": [{"page_url": "https://a.com", "domain": "a.com"}], "requires_manual_review": False, "message": None}
        gv = {"status": "found", "results": [{"page_url": "https://b.com", "domain": "b.com"}], "requires_manual_review": False, "message": None}
        sp = {"status": "found", "results": [{"page_url": "https://c.com", "domain": "c.com"}], "requires_manual_review": False, "message": None}

        result = aggregate(fc, gv, sp)

        assert result["total_raw"] == 3
        assert any(r["page_url"] == "https://c.com" for r in result["results"])

    def test_aggregate_three_sources_with_serpapi_error(self):
        """Erro no SerpAPI não quebra o status quando outras fontes encontraram."""
        from src.search.aggregator import aggregate

        fc = {"status": "found", "results": [{"page_url": "https://a.com", "domain": "a.com"}], "requires_manual_review": False, "message": None}
        gv = {"status": "found", "results": [{"page_url": "https://b.com", "domain": "b.com"}], "requires_manual_review": False, "message": None}
        sp = {"status": "error", "results": [], "requires_manual_review": True, "message": "timeout"}

        result = aggregate(fc, gv, sp)

        assert result["status"] == "found"
        assert result["total_raw"] == 2


# ─── search orchestrator ──────────────────────────────────────────────────────

class TestSearchOrchestrator:

    def _found_result(self, domain="example.com"):
        return {
            "results": [{
                "image_url": None,
                "page_url": f"https://{domain}/page",
                "domain": domain,
                "source": "facecheck",
                "confidence": 0.87,
                "preview_thumbnail": None,
            }],
            "status": "found",
            "requires_manual_review": False,
            "message": None,
        }

    def _error_result(self):
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": "falhou",
        }

    async def test_combines_both_results(self):
        """Orchestrator combina FaceCheck + Vision em resultado unificado."""
        from src.search.orchestrator import search_image

        fc = self._found_result("site-a.com")
        gv = self._found_result("site-b.com")
        gv["results"][0]["source"] = "google_vision"

        with (
            patch("src.search.orchestrator.search_by_face", new=AsyncMock(return_value=fc)),
            patch("src.search.orchestrator.search_by_image", new=AsyncMock(return_value=gv)),
        ):
            result = await search_image("foto.jpg")

        assert result["status"] == "found"
        assert result["total_deduplicated"] == 2
        assert "search_time_seconds" in result
        assert set(result["domains"]) == {"site-a.com", "site-b.com"}

    async def test_error_isolation_facecheck(self):
        """FaceCheck com erro não cancela resultado do Vision."""
        from src.search.orchestrator import search_image

        with (
            patch("src.search.orchestrator.search_by_face", new=AsyncMock(return_value=self._error_result())),
            patch("src.search.orchestrator.search_by_image", new=AsyncMock(return_value=self._found_result())),
        ):
            result = await search_image("foto.jpg")

        assert result["status"] == "partial"
        assert result["total_deduplicated"] == 1

    async def test_error_isolation_vision(self):
        """Vision com erro não cancela resultado do FaceCheck."""
        from src.search.orchestrator import search_image

        with (
            patch("src.search.orchestrator.search_by_face", new=AsyncMock(return_value=self._found_result())),
            patch("src.search.orchestrator.search_by_image", new=AsyncMock(return_value=self._error_result())),
        ):
            result = await search_image("foto.jpg")

        assert result["status"] == "partial"
        assert result["total_deduplicated"] == 1

    async def test_exception_isolation(self):
        """Exceção inesperada no cliente não cancela o resultado inteiro."""
        from src.search.orchestrator import search_image

        with (
            patch("src.search.orchestrator.search_by_face", new=AsyncMock(side_effect=RuntimeError("crash"))),
            patch("src.search.orchestrator.search_by_image", new=AsyncMock(return_value=self._found_result())),
        ):
            result = await search_image("foto.jpg")

        assert result["status"] == "partial"


# ─── rekognition_client ────────────────────────────────────────────────────────

class TestRekognitionClient:

    def test_returns_similarity_when_faces_match(self):
        """compare_faces retorna similarity (0–1) quando rostos são encontrados."""
        from unittest.mock import MagicMock, patch
        from src.search.rekognition_client import compare_faces

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.return_value = {
            "FaceMatches": [{"Similarity": 94.5, "Face": {}}],
            "UnmatchedFaces": [],
        }

        with (
            patch("src.search.rekognition_client._is_configured", True),
            patch("src.search.rekognition_client._get_client", return_value=mock_rekognition),
        ):
            result = compare_faces(b"source_bytes", b"target_bytes")

        assert result["status"] == "found"
        assert abs(result["similarity"] - 0.945) < 0.001

    def test_returns_not_found_when_no_match(self):
        """compare_faces retorna not_found quando não há match de rosto."""
        from unittest.mock import MagicMock, patch
        from src.search.rekognition_client import compare_faces

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.return_value = {
            "FaceMatches": [],
            "UnmatchedFaces": [{"BoundingBox": {}}],
        }

        with (
            patch("src.search.rekognition_client._is_configured", True),
            patch("src.search.rekognition_client._get_client", return_value=mock_rekognition),
        ):
            result = compare_faces(b"source_bytes", b"target_bytes")

        assert result["status"] == "not_found"
        assert result["similarity"] is None

    def test_returns_error_when_no_face_detected(self):
        """compare_faces retorna error quando Rekognition não detecta rosto."""
        from unittest.mock import MagicMock, patch
        from botocore.exceptions import ClientError
        from src.search.rekognition_client import compare_faces

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "No face detected"}},
            "CompareFaces",
        )

        with (
            patch("src.search.rekognition_client._is_configured", True),
            patch("src.search.rekognition_client._get_client", return_value=mock_rekognition),
        ):
            result = compare_faces(b"source_bytes", b"target_bytes")

        assert result["status"] == "error"
        assert result["similarity"] is None

    def test_returns_error_when_credentials_missing(self):
        """compare_faces retorna error quando credenciais AWS não estão configuradas."""
        from unittest.mock import patch
        from src.search.rekognition_client import compare_faces
        with patch("src.search.rekognition_client._is_configured", False):
            result = compare_faces(b"source_bytes", b"target_bytes")
        assert result["status"] == "error"
        assert "credenciais" in result.get("message", "").lower()


# ─── enriquecimento Rekognition ────────────────────────────────────────────────

class TestRekognitionEnrichment:

    def _make_item(self, source="google_vision", image_url=None, thumbnail=None):
        return {
            "image_url": image_url,
            "page_url": "https://example.com/page",
            "domain": "example.com",
            "source": source,
            "confidence": None,
            "preview_thumbnail": thumbnail,
        }

    async def test_enrich_adds_confidence_rekognition_from_thumbnail(self):
        """Item com preview_thumbnail base64 recebe confidence_rekognition."""
        import base64
        from unittest.mock import patch
        from src.search.aggregator import enrich_with_rekognition

        fake_thumbnail = "data:image/jpeg;base64," + base64.b64encode(b"fake_img").decode()
        items = [self._make_item(source="facecheck", thumbnail=fake_thumbnail)]
        mock_compare = {"status": "found", "similarity": 0.92, "message": None}

        with (
            patch("src.search.aggregator._to_jpeg", side_effect=lambda b: b),
            patch("src.search.aggregator.compare_faces", return_value=mock_compare),
        ):
            enriched = await enrich_with_rekognition(items, source_image_bytes=b"source")

        assert enriched[0].get("confidence_rekognition") == 0.92

    async def test_enrich_adds_confidence_rekognition_from_image_url(self):
        """Item com image_url recebe confidence_rekognition via download."""
        from unittest.mock import MagicMock, patch
        from src.search.aggregator import enrich_with_rekognition

        items = [self._make_item(source="google_vision", image_url="https://cdn.example.com/img.jpg")]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"downloaded_image_bytes"
        mock_compare = {"status": "found", "similarity": 0.88, "message": None}

        with (
            patch("httpx.get", return_value=mock_response),
            patch("src.search.aggregator._to_jpeg", side_effect=lambda b: b),
            patch("src.search.aggregator.compare_faces", return_value=mock_compare),
        ):
            enriched = await enrich_with_rekognition(items, source_image_bytes=b"source")

        assert enriched[0].get("confidence_rekognition") == 0.88

    async def test_enrich_skips_item_without_image(self):
        """Item sem thumbnail nem image_url não recebe confidence_rekognition."""
        from src.search.aggregator import enrich_with_rekognition

        items = [self._make_item(source="google_vision", image_url=None, thumbnail=None)]
        enriched = await enrich_with_rekognition(items, source_image_bytes=b"source")

        assert enriched[0].get("confidence_rekognition") is None

    async def test_enrich_handles_rekognition_error_gracefully(self):
        """Erro no Rekognition não interrompe enriquecimento dos outros itens."""
        import base64
        from unittest.mock import patch
        from src.search.aggregator import enrich_with_rekognition

        fake_thumbnail = "data:image/jpeg;base64," + base64.b64encode(b"fake").decode()
        items = [
            self._make_item(source="facecheck", thumbnail=fake_thumbnail),
            self._make_item(source="facecheck", thumbnail=fake_thumbnail),
        ]

        call_count = 0
        def mock_compare(source, target):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "error", "similarity": None, "message": "timeout"}
            return {"status": "found", "similarity": 0.75, "message": None}

        with (
            patch("src.search.aggregator._to_jpeg", side_effect=lambda b: b),
            patch("src.search.aggregator.compare_faces", side_effect=mock_compare),
        ):
            enriched = await enrich_with_rekognition(items, source_image_bytes=b"source")

        assert enriched[0].get("confidence_rekognition") is None
        assert enriched[1].get("confidence_rekognition") == 0.75


# ══════════════════════════════════════════════════════════════════════════════
# Seção 1.6 — Cliente S3 temporário
# ══════════════════════════════════════════════════════════════════════════════


class TestS3TempClient:
    def test_upload_returns_presigned_url(self):
        """Upload bem-sucedido retorna URL presigned e key S3."""
        from unittest.mock import MagicMock, patch
        from src.search.s3_temp_client import upload_and_get_url

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc"

        with (
            patch("src.search.s3_temp_client._BUCKET", "test-bucket"),
            patch("src.search.s3_temp_client._get_client", return_value=mock_s3),
        ):
            url, key = upload_and_get_url(b"fake_image_bytes")

        assert url.startswith("https://s3.amazonaws.com")
        assert key.startswith("temp-search/")
        assert key.endswith(".jpg")
        mock_s3.put_object.assert_called_once()
        mock_s3.generate_presigned_url.assert_called_once()

    def test_delete_removes_object(self):
        """delete_object remove o objeto do bucket."""
        from unittest.mock import MagicMock, patch
        from src.search.s3_temp_client import delete_object

        mock_s3 = MagicMock()

        with (
            patch("src.search.s3_temp_client._BUCKET", "test-bucket"),
            patch("src.search.s3_temp_client._get_client", return_value=mock_s3),
        ):
            delete_object("temp-search/abc.jpg")

        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="temp-search/abc.jpg"
        )

    def test_upload_raises_when_not_configured(self):
        """Sem bucket configurado, levanta RuntimeError descritivo."""
        from unittest.mock import patch
        from src.search.s3_temp_client import upload_and_get_url
        import pytest

        with patch("src.search.s3_temp_client._BUCKET", ""):
            with pytest.raises(RuntimeError, match="AWS_S3_BUCKET"):
                upload_and_get_url(b"fake_image_bytes")


# ══════════════════════════════════════════════════════════════════════════════
# Seção 1.7 — Cliente SerpAPI
# ══════════════════════════════════════════════════════════════════════════════


class TestSerpapiClient:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Busca bem-sucedida retorna lista de resultados no formato padrão."""
        from unittest.mock import MagicMock, patch
        from src.search.serpapi_client import search_by_image_url

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "image_results": [
                {"title": "Página A", "link": "https://site-a.com/page", "source": "site-a.com"},
                {"title": "Página B", "link": "https://site-b.com/page", "source": "site-b.com"},
            ]
        }

        with (
            patch("src.search.serpapi_client._API_KEY", "fake-key"),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__.return_value.get.return_value = mock_response
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

        assert result["status"] == "found"
        assert len(result["results"]) == 2
        assert result["results"][0]["page_url"] == "https://site-a.com/page"
        assert result["results"][0]["source"] == "serpapi"
        assert result["results"][0]["domain"] == "site-a.com"

    @pytest.mark.asyncio
    async def test_search_returns_not_found_when_empty(self):
        """Sem resultados retorna status not_found."""
        from unittest.mock import MagicMock, patch
        from src.search.serpapi_client import search_by_image_url

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"image_results": []}

        with (
            patch("src.search.serpapi_client._API_KEY", "fake-key"),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__.return_value.get.return_value = mock_response
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

        assert result["status"] == "not_found"
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_returns_error_when_not_configured(self):
        """Sem API key retorna status error."""
        from unittest.mock import patch
        from src.search.serpapi_client import search_by_image_url

        with patch("src.search.serpapi_client._API_KEY", ""):
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

        assert result["status"] == "error"
        assert "SERPAPI_KEY" in result["message"]


# ══════════════════════════════════════════════════════════════════════════════
# Seção 2 — Testes de integração com imagens reais (skipados por padrão)
#
# Como usar:
#   1. Preencha TEST_IMAGES com paths de fotos de casos encerrados do Ulysses
#   2. Certifique que FACECHECK_DEMO=true no .env (sem deduzir créditos)
#   3. Execute: pytest tests/test_search.py -m integration -s
# ══════════════════════════════════════════════════════════════════════════════

TEST_IMAGES: list[str] = []
# Preencher com paths locais de imagens de casos encerrados do Ulysses antes de rodar


@pytest.mark.skipif(not TEST_IMAGES, reason="Nenhuma imagem real fornecida")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_image_search_h1_criterion():
    """
    Valida critério de sucesso H1: recall ≥ 70%.
    Requer imagens de casos encerrados do Ulysses em TEST_IMAGES.
    FACECHECK_DEMO=true durante desenvolvimento (sem deduzir créditos).
    """
    from src.search.orchestrator import search_image

    results = []
    for image_path in TEST_IMAGES:
        result = await search_image(image_path)
        results.append(result)

        print(f"\n{'='*60}")
        print(f"IMAGEM: {image_path}")
        print(f"STATUS: {result['status']} | revisão manual: {result['requires_manual_review']}")
        print(f"Tempo:  {result.get('search_time_seconds')}s")
        print(f"Resultados: {result['total_deduplicated']} (de {result['total_raw']} brutos)")
        print(f"Domínios: {', '.join(result['domains'][:10]) or '—'}")

        for r in result["results"][:5]:
            print(f"  [{r['source']}] conf={r['confidence']} → {r['page_url']}")

        if result.get("message"):
            print(f"  ⚠ {result['message']}")

    for r in results:
        for key in ("results", "domains", "total_raw", "total_deduplicated",
                    "search_time_seconds", "status", "requires_manual_review"):
            assert key in r, f"Chave ausente: {key}"

    # Critério H1: ≥ 70% com pelo menos 1 resultado encontrado
    success = [r for r in results if r["status"] in ("found", "partial") and r["total_deduplicated"] > 0]
    rate = len(success) / len(results)
    print(f"\nTaxa de sucesso H1: {rate:.0%} ({len(success)}/{len(results)})")
    assert rate >= 0.70, f"H1 não atingido: {rate:.0%} < 70%"
