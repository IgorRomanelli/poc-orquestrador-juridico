"""
Tests for src/main.py — FastAPI app with 4 endpoints.

Coverage:
1. Missing X-API-Secret → 401
2. Wrong X-API-Secret → 401
3. POST /search with valid image → returns {"job_id": "..."}
4. GET /status with unknown job_id → 404
5. GET /status with known job_id in "processing" state → {"status": "processing"}
6. GET /lookup/{domain} → calls lookup_domain and returns result
"""

import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("API_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ORIGIN", "http://localhost:3000")
    # Reload app so env vars are picked up fresh
    import importlib
    import src.main as main_module
    importlib.reload(main_module)
    # Re-patch jobs dict to be empty
    main_module.jobs.clear()


@pytest.fixture
def client():
    import src.main as main_module
    return TestClient(main_module.app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    return {"X-API-Secret": "test-secret"}


# ─── Auth tests ───────────────────────────────────────────────────────────────

def test_missing_api_secret_returns_401(client):
    response = client.post("/search", files={"image": ("test.jpg", b"fake", "image/jpeg")})
    assert response.status_code == 401


def test_wrong_api_secret_returns_401(client):
    response = client.post(
        "/search",
        files={"image": ("test.jpg", b"fake", "image/jpeg")},
        headers={"X-API-Secret": "wrong-secret"},
    )
    assert response.status_code == 401


def test_missing_secret_on_status_returns_401(client):
    response = client.get("/status/some-job-id")
    assert response.status_code == 401


def test_missing_secret_on_lookup_returns_401(client):
    response = client.get("/lookup/example.com")
    assert response.status_code == 401


# ─── POST /search ─────────────────────────────────────────────────────────────

def test_post_search_returns_job_id(client, auth_headers):
    fake_results = [{"page_url": "https://example.com/page", "image_url": "https://example.com/img.jpg", "confidence": 0.9, "source": "facecheck"}]

    with patch("src.main.run_full_search", new=AsyncMock(return_value=fake_results)):
        response = client.post(
            "/search",
            files={"image": ("test.jpg", b"\xff\xd8\xff" + b"\x00" * 10, "image/jpeg")},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    # Validate it looks like a UUID
    uuid.UUID(body["job_id"])


# ─── GET /status ──────────────────────────────────────────────────────────────

def test_status_unknown_job_returns_404(client, auth_headers):
    response = client.get("/status/nonexistent-job-id", headers=auth_headers)
    assert response.status_code == 404


def test_status_processing_returns_state(client, auth_headers):
    import src.main as main_module

    job_id = str(uuid.uuid4())
    main_module.jobs[job_id] = {"status": "processing"}

    response = client.get(f"/status/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_status_done_returns_results(client, auth_headers):
    import src.main as main_module

    job_id = str(uuid.uuid4())
    main_module.jobs[job_id] = {
        "status": "done",
        "results": [],
        "total": 0,
        "search_time_seconds": 1.23,
    }

    response = client.get(f"/status/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert "results" in body


# ─── GET /lookup ──────────────────────────────────────────────────────────────

def test_lookup_domain_calls_and_returns(client, auth_headers):
    mock_result = {
        "domain": "example.com",
        "status": "found",
        "requires_manual_review": False,
        "summary": {"razao_social": "Empresa Exemplo", "cnpj": "12.345.678/0001-99"},
    }

    with patch("src.main.lookup_domain", new=AsyncMock(return_value=mock_result)):
        response = client.get("/lookup/example.com", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"
    assert response.json()["status"] == "found"


# ─── POST /dossie ─────────────────────────────────────────────────────────────

def test_dossie_returns_pdf_and_caches_duplicate_domains(client, auth_headers):
    mock_lookup_result = {"domain": "example.com", "status": "found"}
    fake_pdf_bytes = b"%PDF-fake"

    results = [
        {"domain": "example.com", "pageUrl": "https://example.com/page1", "confidence": 90},
        {"domain": "other.com", "pageUrl": "https://other.com/page", "confidence": 70},
        {"domain": "example.com", "pageUrl": "https://example.com/page2", "confidence": 85},
    ]

    with patch("src.main.lookup_domain", new=AsyncMock(return_value=mock_lookup_result)) as mock_lookup, \
         patch("src.main.pdf_to_bytes", return_value=fake_pdf_bytes):
        response = client.post(
            "/dossie",
            json={"client_name": "Ulysses", "results": results},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    # lookup_domain should be called once per unique domain (2), not once per result (3)
    assert mock_lookup.call_count == 2
