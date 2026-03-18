# SerpAPI Google Reverse Image Search — Plano de Integração

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar SerpAPI como fonte complementar de busca reversa de imagem, paralela ao FaceCheck e Google Vision, aumentando o recall de resultados.

**Architecture:** Um novo cliente `s3_temp_client.py` faz upload temporário da imagem para um bucket S3 privado e gera uma presigned URL com expiração de 60 segundos. O cliente `serpapi_client.py` usa essa URL para consultar o SerpAPI Google Reverse Image. Após a busca, a imagem é deletada do S3. O resultado é integrado ao fluxo existente via `aggregate()` no `app.py`, rodando em paralelo com as outras fontes.

**Tech Stack:** SerpAPI REST API, AWS S3 (presigned URLs via boto3 — já instalado), variáveis de ambiente `SERPAPI_KEY` e `AWS_S3_BUCKET` (as credenciais AWS já existem no `.env`).

> ✅ **Segurança:** A foto permanece em infraestrutura privada (seu bucket S3). A presigned URL expira em 60 segundos e o objeto é deletado após a busca. Nenhuma imagem vai para serviços públicos de terceiros.

---

## Pré-requisito: criar bucket S3

Antes de executar o plano, crie um bucket S3 privado:

1. Acesse [console.aws.amazon.com/s3](https://console.aws.amazon.com/s3)
2. Clique em **Create bucket**
3. Nome: `poc-dossie-temp` (ou qualquer nome único)
4. Região: `us-east-1` (mesma do Rekognition)
5. Mantenha **Block all public access** ativado
6. Clique em **Create bucket**
7. Adicione ao `.env`: `AWS_S3_BUCKET=poc-dossie-temp`

---

## Estrutura de arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `src/search/s3_temp_client.py` | Criar | Upload → presigned URL → delete no S3 |
| `src/search/serpapi_client.py` | Criar | Busca reversa via SerpAPI usando URL |
| `src/ui/app.py` | Modificar | Adicionar SerpAPI ao fluxo paralelo de busca |
| `tests/test_search.py` | Modificar | Testes dos dois novos clientes |
| `.env.example` | Modificar | Documentar as novas variáveis |

---

## Task 1: Cliente S3 temporário

**Files:**
- Create: `src/search/s3_temp_client.py`
- Test: `tests/test_search.py` (classe `TestS3TempClient`)

### Contexto

O cliente usa `boto3` (já instalado) com as credenciais AWS existentes (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`). Nova variável: `AWS_S3_BUCKET`.

Fluxo: `upload_and_get_url(bytes)` → faz `put_object` no S3 com key `temp-search/<uuid>.jpg` → gera presigned URL com `ExpiresIn=60` → retorna `(url, key)`. A key é usada depois para deletar o objeto via `delete_object(key)`.

- [ ] **Step 1: Escrever os testes**

```python
# tests/test_search.py — adicionar classe TestS3TempClient

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
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

```bash
python3 -m pytest tests/test_search.py::TestS3TempClient -v
```
Esperado: `ERROR` (módulo não existe ainda)

- [ ] **Step 3: Criar `src/search/s3_temp_client.py`**

```python
"""
Cliente S3 temporário — hospedagem segura de imagem para obter presigned URL.

Necessário porque SerpAPI aceita apenas image_url, não upload direto.
A imagem fica em bucket S3 privado com presigned URL de 60 segundos.
O objeto é deletado após o uso.

Variáveis de ambiente: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
                       AWS_REGION (default: us-east-1), AWS_S3_BUCKET
"""

import os
import uuid

import boto3
from dotenv import load_dotenv

load_dotenv()

_BUCKET = os.getenv("AWS_S3_BUCKET", "")
_REGION = os.getenv("AWS_REGION", "us-east-1")
_EXPIRATION_SECONDS = 60


def _get_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=_REGION,
    )


def upload_and_get_url(image_bytes: bytes) -> tuple[str, str]:
    """
    Faz upload de imagem para S3 e retorna (presigned_url, s3_key).

    Args:
        image_bytes: bytes da imagem em formato JPEG.

    Returns:
        Tupla (url, key) onde url expira em 60 segundos.

    Raises:
        RuntimeError: se AWS_S3_BUCKET não configurado.
    """
    if not _BUCKET:
        raise RuntimeError("AWS_S3_BUCKET não configurado — configure no .env")

    key = f"temp-search/{uuid.uuid4()}.jpg"
    client = _get_client()

    client.put_object(
        Bucket=_BUCKET,
        Key=key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_EXPIRATION_SECONDS,
    )

    return url, key


def delete_object(key: str) -> None:
    """Remove objeto do bucket S3 após o uso."""
    client = _get_client()
    client.delete_object(Bucket=_BUCKET, Key=key)
```

- [ ] **Step 4: Rodar os testes para confirmar aprovação**

```bash
python3 -m pytest tests/test_search.py::TestS3TempClient -v
```
Esperado: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/search/s3_temp_client.py tests/test_search.py
git commit -m "feat(search): adicionar cliente S3 temporário para presigned URL"
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

Resposta relevante: `image_results` (lista de páginas com a imagem).

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
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

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
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

        assert result["status"] == "not_found"
        assert result["results"] == []

    async def test_search_returns_error_when_not_configured(self):
        """Sem API key retorna status error."""
        from unittest.mock import patch
        from src.search.serpapi_client import search_by_image_url

        with patch("src.search.serpapi_client._API_KEY", ""):
            result = await search_by_image_url("https://s3.amazonaws.com/bucket/key?sig=abc")

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

Recebe uma URL pública de imagem (presigned URL do S3) e retorna lista de
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
        image_url: presigned URL do S3 (expira em 60s).

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
- Modify: `src/search/aggregator.py`

### Contexto

O `app.py` roda FaceCheck e Google Vision em paralelo via `ThreadPoolExecutor`. O SerpAPI precisa de dois passos sequenciais:
1. Upload da imagem ao S3 + geração de presigned URL (`upload_and_get_url` — síncrono, em thread)
2. Busca no SerpAPI usando a URL (`search_by_image_url` — assíncrono, com `asyncio.run`)
3. Deleção do objeto S3 após a busca (`delete_object`)

O SerpAPI só roda se `SERPAPI_KEY` estiver configurada. Se não estiver, é ignorado silenciosamente.

O `aggregate()` atual aceita apenas dois argumentos — precisa ser atualizado para aceitar múltiplas fontes.

### Atualização necessária no `aggregate()`

```python
# Assinatura atual:
def aggregate(facecheck_result: dict, vision_result: dict) -> dict:

# Nova assinatura (retrocompatível — caller existente passa 2 args, continua funcionando):
def aggregate(*source_results: dict) -> dict:
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

    seen_page_urls: set[str] = set()
    deduplicated = []
    for item in all_items:
        page_url = item.get("page_url", "")
        if page_url and page_url not in seen_page_urls:
            seen_page_urls.add(page_url)
            deduplicated.append(item)

    deduplicated.sort(key=_confidence_key)

    domains: list[str] = []
    seen_domains: set[str] = set()
    for item in deduplicated:
        d = item.get("domain", "")
        if d and d not in seen_domains:
            seen_domains.add(d)
            domains.append(d)

    # Status determinado pelas duas primeiras fontes (FaceCheck + Vision)
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

Localizar o bloco de imports em `src/ui/app.py`:
```python
from src.search.aggregator import aggregate, enrich_with_rekognition
from src.search.facecheck_client import search_by_face
from src.search.google_vision_client import search_by_image
from src.search.orchestrator import search_image  # fallback
from src.search.rekognition_client import _is_configured as _rekognition_configured
```

Adicionar após:
```python
from src.search.s3_temp_client import delete_object as _s3_delete
from src.search.s3_temp_client import upload_and_get_url as _s3_upload
from src.search.s3_temp_client import _BUCKET as _s3_bucket
from src.search.serpapi_client import search_by_image_url as _serpapi_search
from src.search.serpapi_client import _API_KEY as _serpapi_key
```

Localizar o bloco de busca e adicionar antes do `ThreadPoolExecutor`:
```python
_serpapi_enabled = bool(_serpapi_key and _s3_bucket)
sp_result = {"status": "not_found", "results": [], "requires_manual_review": False, "message": None}
sp_shown = False
```

Adicionar placeholder no `st.status`:
```python
if _serpapi_enabled:
    ph_sp = st.empty()
    ph_sp.info("⏳ SerpAPI: aguardando...")
```

Adicionar função `_run_serpapi` antes do executor:
```python
def _run_serpapi():
    if not _serpapi_enabled:
        return sp_result
    s3_key = None
    try:
        image_url, s3_key = _s3_upload(uploaded_file.getvalue())
        return _asyncio.run(_serpapi_search(image_url))
    except Exception as exc:
        return {"status": "error", "results": [], "requires_manual_review": True, "message": str(exc)}
    finally:
        if s3_key:
            try:
                _s3_delete(s3_key)
            except Exception:
                pass
```

Adicionar ao `ThreadPoolExecutor` e polling:
```python
sp_future = executor.submit(_run_serpapi)

# No loop de polling:
if _serpapi_enabled and sp_future.done() and not sp_shown:
    sp_result = sp_future.result()
    n = len(sp_result.get("results", []))
    ph_sp.success(f"✅ SerpAPI: {n} resultado(s)")
    sp_shown = True
```

Atualizar a chamada ao `aggregate`:
```python
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

# AWS S3 — bucket privado para presigned URL temporária (SerpAPI)
# Criar bucket em: console.aws.amazon.com/s3 (manter Block all public access ativado)
AWS_S3_BUCKET=poc-dossie-temp
```

- [ ] **Step 2: Adicionar os valores reais ao `.env` local**

```bash
SERPAPI_KEY=sua_chave_serpapi
AWS_S3_BUCKET=nome-do-seu-bucket
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: documentar variáveis SERPAPI_KEY e AWS_S3_BUCKET no .env.example"
```

---

## Verificação final

```bash
python3 -m pytest tests/ -q
```
Esperado: todos os testes passando (sem regressão).

---

## Como testar manualmente

1. Crie o bucket S3 (veja Pré-requisito acima)
2. Cadastre-se em [serpapi.com](https://serpapi.com) → Dashboard → copie a API key (100 buscas grátis)
3. Adicione ao `.env`:
   ```
   SERPAPI_KEY=sua_chave
   AWS_S3_BUCKET=nome-do-seu-bucket
   ```
4. Reinicie o app: `DYLD_LIBRARY_PATH=/opt/homebrew/lib streamlit run src/ui/app.py`
5. Faça uma busca — deve aparecer "✅ SerpAPI: N resultado(s)" na tela de progresso
