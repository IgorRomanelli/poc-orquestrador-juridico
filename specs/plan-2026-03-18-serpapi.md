# SerpAPI Google Reverse Image Search — Plano de Integração

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar SerpAPI como fonte complementar de busca reversa de imagem, paralela ao FaceCheck e Google Vision, aumentando o recall de resultados.

**Architecture:** Um novo cliente `serpapi_client.py` faz upload temporário da imagem via ImgBB (gratuito, expira automaticamente) para obter uma URL pública, depois consulta SerpAPI Google Reverse Image com essa URL. O resultado é integrado ao fluxo existente via `aggregate()` no `app.py`, rodando em paralelo com as outras fontes. O `orchestrator.py` não é modificado — a busca do app já contorna o orquestrador.

**Tech Stack:** SerpAPI REST API, ImgBB API (hosting temporário), httpx, variáveis de ambiente `SERPAPI_KEY` e `IMGBB_KEY`.

> ⚠️ **Nota de privacidade:** A foto do cliente é enviada ao ImgBB (hosting temporário) e ao SerpAPI (terceiros). Na POC isso é aceitável — a foto já vai ao FaceCheck e Google Vision. Em produção, substituir ImgBB por storage privado com signed URL (ex: S3 presigned URL).

---

## Estrutura de arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `src/search/imgbb_client.py` | Criar | Upload de imagem → URL temporária |
| `src/search/serpapi_client.py` | Criar | Busca reversa via SerpAPI usando URL |
| `src/ui/app.py` | Modificar | Adicionar SerpAPI ao fluxo paralelo de busca |
| `tests/test_search.py` | Modificar | Testes dos dois novos clientes |
| `.env.example` | Modificar | Documentar as novas variáveis |
| `requirements.txt` | Verificar | httpx já está presente |

---

## Task 1: Cliente ImgBB

**Files:**
- Create: `src/search/imgbb_client.py`
- Test: `tests/test_search.py` (classe `TestImgbbClient`)

### Contexto

ImgBB API: `POST https://api.imgbb.com/1/upload` com `key=API_KEY&image=BASE64` (multipart ou form-encoded). Retorna `{"data": {"url": "...", "delete_url": "..."}}`. Imagens expiram em 60 segundos com o parâmetro `expiration=60`.

Cadastro gratuito em imgbb.com → API Key em Account > API.

- [ ] **Step 1: Escrever o teste para upload bem-sucedido**

```python
# tests/test_search.py — adicionar dentro de uma nova classe TestImgbbClient

class TestImgbbClient:
    def test_upload_returns_url(self):
        """Upload bem-sucedido retorna URL pública."""
        from unittest.mock import MagicMock, patch
        from src.search.imgbb_client import upload_image

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"url": "https://i.ibb.co/abc/photo.jpg"},
            "success": True,
        }

        with (
            patch("src.search.imgbb_client._API_KEY", "fake-key"),
            patch("httpx.post", return_value=mock_response),
        ):
            url = upload_image(b"fake_image_bytes")

        assert url == "https://i.ibb.co/abc/photo.jpg"

    def test_upload_raises_on_api_error(self):
        """Erro de API levanta RuntimeError."""
        from unittest.mock import MagicMock, patch
        from src.search.imgbb_client import upload_image
        import pytest

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"success": False, "error": {"message": "bad key"}}

        with (
            patch("src.search.imgbb_client._API_KEY", "fake-key"),
            patch("httpx.post", return_value=mock_response),
        ):
            with pytest.raises(RuntimeError, match="ImgBB"):
                upload_image(b"fake_image_bytes")

    def test_upload_raises_when_not_configured(self):
        """Sem API key, levanta RuntimeError descritivo."""
        from unittest.mock import patch
        from src.search.imgbb_client import upload_image
        import pytest

        with patch("src.search.imgbb_client._API_KEY", ""):
            with pytest.raises(RuntimeError, match="IMGBB_KEY"):
                upload_image(b"fake_image_bytes")
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

```bash
python3 -m pytest tests/test_search.py::TestImgbbClient -v
```
Esperado: `ERROR` (módulo não existe ainda)

- [ ] **Step 3: Criar `src/search/imgbb_client.py`**

```python
"""
Cliente ImgBB — hospedagem temporária de imagem para obter URL pública.

Necessário porque SerpAPI aceita apenas image_url, não upload direto.
Imagens expiram em 60 segundos após o upload.

Variável de ambiente: IMGBB_KEY
"""

import base64
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("IMGBB_KEY", "")
_UPLOAD_URL = "https://api.imgbb.com/1/upload"
_EXPIRATION_SECONDS = 60


def upload_image(image_bytes: bytes) -> str:
    """
    Faz upload de imagem para ImgBB e retorna URL pública temporária.

    Args:
        image_bytes: bytes da imagem (JPEG, PNG, WebP, etc.)

    Returns:
        URL pública da imagem (expira em 60s).

    Raises:
        RuntimeError: se IMGBB_KEY não configurada ou upload falhar.
    """
    if not _API_KEY:
        raise RuntimeError("IMGBB_KEY não configurada — configure no .env")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = httpx.post(
        _UPLOAD_URL,
        data={
            "key": _API_KEY,
            "image": b64,
            "expiration": _EXPIRATION_SECONDS,
        },
        timeout=15.0,
    )

    payload = response.json()
    if response.status_code != 200 or not payload.get("success"):
        msg = payload.get("error", {}).get("message", str(response.status_code))
        raise RuntimeError(f"ImgBB upload falhou: {msg}")

    return payload["data"]["url"]
```

- [ ] **Step 4: Rodar os testes para confirmar aprovação**

```bash
python3 -m pytest tests/test_search.py::TestImgbbClient -v
```
Esperado: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/search/imgbb_client.py tests/test_search.py
git commit -m "feat(search): adicionar cliente ImgBB para hosting temporário de imagem"
```

---

## Task 2: Cliente SerpAPI

**Files:**
- Create: `src/search/serpapi_client.py`
- Test: `tests/test_search.py` (classe `TestSerpapiClient`)

### Contexto

SerpAPI endpoint: `GET https://serpapi.com/search` com parâmetros:
- `engine=google_reverse_image`
- `image_url=<url>`
- `api_key=<key>`

Resposta relevante: `image_results` (lista de páginas com a imagem) e `inline_images` (imagens visualmente similares).

Cada `image_result`:
```json
{
  "title": "...",
  "link": "https://exemplo.com/pagina",
  "snippet": "...",
  "source": "exemplo.com"
}
```

O resultado deve seguir o mesmo formato dos outros clientes:
```python
{
    "page_url": item["link"],
    "domain": extract_domain(item["link"]),
    "source": "serpapi",
    "confidence": None,
    "preview_thumbnail": "",
    "image_url": "",
}
```

- [ ] **Step 1: Escrever os testes**

```python
# tests/test_search.py — adicionar classe TestSerpapiClient

class TestSerpapiClient:
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
            result = await search_by_image_url("https://i.ibb.co/abc/photo.jpg")

        assert result["status"] == "found"
        assert len(result["results"]) == 2
        assert result["results"][0]["page_url"] == "https://site-a.com/page"
        assert result["results"][0]["source"] == "serpapi"
        assert result["results"][0]["domain"] == "site-a.com"

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
            result = await search_by_image_url("https://i.ibb.co/abc/photo.jpg")

        assert result["status"] == "not_found"
        assert result["results"] == []

    async def test_search_returns_error_when_not_configured(self):
        """Sem API key retorna status error."""
        from unittest.mock import patch
        from src.search.serpapi_client import search_by_image_url

        with patch("src.search.serpapi_client._API_KEY", ""):
            result = await search_by_image_url("https://example.com/img.jpg")

        assert result["status"] == "error"
        assert "SERPAPI_KEY" in result["message"]
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

```bash
python3 -m pytest tests/test_search.py::TestSerpapiClient -v
```
Esperado: `ERROR` (módulo não existe ainda)

- [ ] **Step 3: Criar `src/search/serpapi_client.py`**

```python
"""
Cliente SerpAPI — busca reversa de imagem via Google Reverse Image Search.

Recebe uma URL pública de imagem (obtida via ImgBB) e retorna lista de
páginas onde a imagem aparece, no mesmo formato dos outros clientes.

Variável de ambiente: SERPAPI_KEY
"""

import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("SERPAPI_KEY", "")
_SEARCH_URL = "https://serpapi.com/search"


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


async def search_by_image_url(image_url: str) -> dict:
    """
    Busca páginas que contêm a imagem usando SerpAPI Google Reverse Image.

    Args:
        image_url: URL pública da imagem (ex: obtida via ImgBB).

    Returns:
        dict com status, results e message (mesmo formato dos outros clientes).
    """
    if not _API_KEY:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": "SERPAPI_KEY não configurada — configure no .env",
        }

    params = {
        "engine": "google_reverse_image",
        "image_url": image_url,
        "api_key": _API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "results": [],
            "status": "error",
            "requires_manual_review": True,
            "message": f"SerpAPI falhou: {exc}",
        }

    raw_results = data.get("image_results", [])
    results = [
        {
            "page_url": item.get("link", ""),
            "domain": _extract_domain(item.get("link", "")),
            "source": "serpapi",
            "confidence": None,
            "preview_thumbnail": "",
            "image_url": "",
        }
        for item in raw_results
        if item.get("link")
    ]

    return {
        "results": results,
        "status": "found" if results else "not_found",
        "requires_manual_review": False,
        "message": None,
    }
```

- [ ] **Step 4: Rodar os testes**

```bash
python3 -m pytest tests/test_search.py::TestSerpapiClient -v
```
Esperado: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/search/serpapi_client.py tests/test_search.py
git commit -m "feat(search): adicionar cliente SerpAPI para busca reversa complementar"
```

---

## Task 3: Integrar SerpAPI no fluxo de busca do app.py

**Files:**
- Modify: `src/ui/app.py`

### Contexto

O `app.py` roda FaceCheck e Google Vision em paralelo via `ThreadPoolExecutor`, depois chama `aggregate()`. O SerpAPI precisa de dois passos sequenciais:
1. Upload da imagem ao ImgBB (`upload_image` — síncrono, em thread)
2. Busca no SerpAPI (`search_by_image_url` — assíncrono, em thread com `asyncio.run`)

O SerpAPI só roda se `SERPAPI_KEY` estiver configurada. Se não estiver, é ignorado silenciosamente.

O `aggregate()` atual aceita apenas dois argumentos (`facecheck_result`, `vision_result`). Ele precisa ser atualizado para aceitar múltiplas fontes via `*args` ou receber uma lista.

### Atualização necessária no `aggregate()`

```python
# src/search/aggregator.py — assinatura atual:
def aggregate(facecheck_result: dict, vision_result: dict) -> dict:
    all_items = []
    all_items.extend(facecheck_result.get("results", []))
    all_items.extend(vision_result.get("results", []))
    ...

# Nova assinatura (retrocompatível):
def aggregate(*source_results: dict) -> dict:
    all_items = []
    for r in source_results:
        all_items.extend(r.get("results", []))
    ...
```

- [ ] **Step 1: Escrever testes para aggregate com 3 fontes**

```python
# tests/test_search.py — adicionar em TestAggregator

def test_aggregate_three_sources(self):
    """aggregate aceita três fontes e une todos os resultados."""
    fc = {"status": "found", "results": [{"page_url": "https://a.com", "domain": "a.com"}], "requires_manual_review": False, "message": None}
    gv = {"status": "found", "results": [{"page_url": "https://b.com", "domain": "b.com"}], "requires_manual_review": False, "message": None}
    sp = {"status": "found", "results": [{"page_url": "https://c.com", "domain": "c.com"}], "requires_manual_review": False, "message": None}

    result = aggregate(fc, gv, sp)

    assert result["total_raw"] == 3
    assert any(r["page_url"] == "https://c.com" for r in result["results"])

def test_aggregate_three_sources_with_serpapi_error(self):
    """Erro no SerpAPI não quebra o status quando outras fontes encontraram."""
    fc = {"status": "found", "results": [{"page_url": "https://a.com", "domain": "a.com"}], "requires_manual_review": False, "message": None}
    gv = {"status": "found", "results": [{"page_url": "https://b.com", "domain": "b.com"}], "requires_manual_review": False, "message": None}
    sp = {"status": "error", "results": [], "requires_manual_review": True, "message": "timeout"}

    result = aggregate(fc, gv, sp)

    # Status é determinado pelas duas primeiras fontes (fc + gv encontraram)
    assert result["status"] == "found"
    assert result["total_raw"] == 2
```

- [ ] **Step 2: Rodar o teste para confirmar falha**

```bash
python3 -m pytest tests/test_search.py -k "test_aggregate_three_sources" -v
```
Esperado: FAIL

- [ ] **Step 3: Atualizar `aggregate()` em `src/search/aggregator.py`**

Localizar as linhas:
```python
def aggregate(facecheck_result: dict, vision_result: dict) -> dict:
    ...
    all_items = []
    all_items.extend(facecheck_result.get("results", []))
    all_items.extend(vision_result.get("results", []))
    ...
    status, requires_manual = _compute_status(facecheck_result, vision_result)
    message = _collect_messages(facecheck_result, vision_result)
```

Substituir por:
```python
def aggregate(*source_results: dict) -> dict:
    """
    Agrega, deduplica e ordena resultados de múltiplas fontes de busca.

    Args:
        *source_results: dicts retornados por qualquer cliente de busca.

    Returns:
        dict consolidado com results, domains, contagens e status global.
    """
    all_items = []
    for r in source_results:
        all_items.extend(r.get("results", []))

    total_raw = len(all_items)

    # Deduplicar por page_url (primeira ocorrência vence)
    seen_page_urls: set[str] = set()
    deduplicated = []
    for item in all_items:
        page_url = item.get("page_url", "")
        if page_url and page_url not in seen_page_urls:
            seen_page_urls.add(page_url)
            deduplicated.append(item)

    # Ordenar por confidence desc (None vai para o final)
    deduplicated.sort(key=_confidence_key)

    # Extrair domínios únicos preservando ordem de aparição
    domains: list[str] = []
    seen_domains: set[str] = set()
    for item in deduplicated:
        d = item.get("domain", "")
        if d and d not in seen_domains:
            seen_domains.add(d)
            domains.append(d)

    # Usar apenas os dois primeiros para _compute_status/_collect_messages
    # (compatibilidade com lógica de status FaceCheck vs Vision)
    first = source_results[0] if source_results else {}
    second = source_results[1] if len(source_results) > 1 else {}
    status, requires_manual = _compute_status(first, second)
    message = _collect_messages(first, second)

    return {
        "results": deduplicated,
        "domains": domains,
        "total_raw": total_raw,
        "total_deduplicated": len(deduplicated),
        "status": status,
        "requires_manual_review": requires_manual,
        "message": message,
    }
```

- [ ] **Step 4: Rodar todos os testes para confirmar sem regressão**

```bash
python3 -m pytest tests/ -q
```
Esperado: todos passando

- [ ] **Step 5: Adicionar SerpAPI ao fluxo em `app.py`** e corrigir `_source_label`

Localizar em `src/ui/app.py` a função `_source_label` e adicionar o caso SerpAPI:
```python
# Antes:
return "FaceCheck" if source == "facecheck" else "Google Vision"
# Depois:
if source == "facecheck":
    return "FaceCheck"
if source == "serpapi":
    return "SerpAPI"
return "Google Vision"
```

Localizar em `src/ui/app.py`:
```python
from src.search.aggregator import aggregate, enrich_with_rekognition
from src.search.facecheck_client import search_by_face
from src.search.google_vision_client import search_by_image
from src.search.orchestrator import search_image  # fallback
from src.search.rekognition_client import _is_configured as _rekognition_configured
```

Adicionar:
```python
from src.search.imgbb_client import upload_image as _imgbb_upload
from src.search.serpapi_client import search_by_image_url as _serpapi_search
from src.search.serpapi_client import _API_KEY as _serpapi_configured
```

Localizar o bloco de busca paralela e adicionar SerpAPI:
```python
# Após os placeholders de FaceCheck e Google Vision:
ph_sp = st.empty()
_serpapi_enabled = bool(_serpapi_configured)
if _serpapi_enabled:
    ph_sp.info("⏳ SerpAPI: aguardando...")

# Inicializar sp_result antes do executor (assim como fc_result = _err e gv_result = _err)
sp_result = {"status": "not_found", "results": [], "requires_manual_review": False, "message": None}
sp_shown = False

def _run_serpapi():
    if not _serpapi_enabled:
        return {"status": "not_found", "results": [], "requires_manual_review": False, "message": None}
    try:
        image_url = _imgbb_upload(uploaded_file.getvalue())
        return _asyncio.run(_serpapi_search(image_url))
    except Exception as exc:
        return {"status": "error", "results": [], "requires_manual_review": True, "message": str(exc)}

# Adicionar ao ThreadPoolExecutor:
sp_future = executor.submit(_run_serpapi)

# No loop de polling, adicionar:
if sp_future.done() and _serpapi_enabled and not sp_shown:
    sp_result = sp_future.result()
    n = len(sp_result.get("results", []))
    ph_sp.success(f"✅ SerpAPI: {n} resultado(s)")
    sp_shown = True

# Atualizar chamada ao aggregate:
result = aggregate(fc_result, gv_result, sp_result)
```

- [ ] **Step 6: Rodar todos os testes**

```bash
python3 -m pytest tests/ -q
```
Esperado: todos passando

- [ ] **Step 7: Commit**

```bash
git add src/search/aggregator.py src/ui/app.py tests/test_search.py
git commit -m "feat(search): integrar SerpAPI como fonte complementar de busca reversa"
```

---

## Task 4: Documentar variáveis de ambiente

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Adicionar as novas chaves ao `.env.example`**

```bash
# SerpAPI — busca reversa complementar (google_reverse_image)
# Cadastro: https://serpapi.com → 100 buscas grátis/mês
SERPAPI_KEY=...

# ImgBB — hosting temporário de imagem para SerpAPI
# Cadastro: https://imgbb.com → Account > API (gratuito)
IMGBB_KEY=...
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: documentar variáveis SERPAPI_KEY e IMGBB_KEY no .env.example"
```

---

## Verificação final

```bash
python3 -m pytest tests/ -q
```
Esperado: todos os testes passando (sem regressão).

---

## Como testar manualmente

1. Cadastre-se em [imgbb.com](https://imgbb.com) → Account > API → copie a chave
2. Cadastre-se em [serpapi.com](https://serpapi.com) → Dashboard → copie a API key (100 buscas grátis)
3. Adicione ao `.env` (não só ao `.env.example`):
   ```
   IMGBB_KEY=sua_chave_imgbb
   SERPAPI_KEY=sua_chave_serpapi
   ```
4. Reinicie o app: `DYLD_LIBRARY_PATH=/opt/homebrew/lib streamlit run src/ui/app.py`
5. Faça uma busca — deve aparecer "✅ SerpAPI: N resultado(s)" na tela de progresso
