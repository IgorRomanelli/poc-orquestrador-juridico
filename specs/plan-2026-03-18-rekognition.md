# Amazon Rekognition — Verificador de Confiança Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Usar Amazon Rekognition `CompareFaces` como verificador de confiança para enriquecer os resultados do Google Vision (que chegam sem score) e do FaceCheck com uma similaridade facial independente.

**Architecture:** Após FaceCheck + Google Vision retornarem resultados agregados, um novo passo de enriquecimento chama o Rekognition `CompareFaces` para cada item que possui imagem acessível (`preview_thumbnail` base64 ou `image_url`). O resultado é armazenado em `confidence_rekognition` no item — não substitui `confidence`, apenas complementa. O enriquecimento é opcional: se `AWS_ACCESS_KEY_ID` não estiver configurada, o passo é silenciosamente ignorado.

**Tech Stack:** `boto3` (AWS SDK para Python), `httpx` (download de imagens por URL), `asyncio.to_thread` (boto3 é síncrono — executa em thread pool), variáveis de ambiente `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (default: `us-east-1`).

---

## Arquivos

| Ação | Arquivo | Responsabilidade |
|------|---------|-----------------|
| Criar | `src/search/rekognition_client.py` | Chama `CompareFaces` via boto3; retorna similaridade ou erro |
| Modificar | `src/search/aggregator.py` | Adiciona `enrich_with_rekognition(items, source_image_path)` |
| Modificar | `src/search/orchestrator.py` | Chama enriquecimento após `aggregate()` |
| Modificar | `src/ui/app.py` | Exibe `confidence_rekognition` no card e no label de confiança |
| Modificar | `src/export/dossie_generator.py` | Inclui score Rekognition no campo "Confiança da busca" do dossiê |
| Modificar | `tests/test_search.py` | Adiciona `TestRekognitionClient` e testes de enriquecimento |
| Modificar | `.env.example` (se existir) ou `README` | Documenta as 3 variáveis AWS necessárias |

---

## Contexto da codebase (leia antes de codar)

### Estrutura padrão de um item de resultado
```python
{
    "image_url": "https://cdn.example.com/foto.jpg",  # URL direta — Google Vision; None no FaceCheck
    "page_url": "https://example.com/page",
    "domain": "example.com",
    "source": "facecheck" | "google_vision",
    "confidence": 0.87,          # FaceCheck: 0–1; Google Vision: sempre None
    "preview_thumbnail": "data:image/jpeg;base64,...",  # FaceCheck: base64; Google Vision: None
}
```

### Após enriquecimento, o item ganha um campo extra:
```python
{
    ...todos os campos acima...,
    "confidence_rekognition": 0.94,  # similaridade Rekognition (0–1), ou None se falhou
}
```

### Padrão de resultado dos clientes de busca
```python
# Sucesso
{"results": [...], "status": "found", "requires_manual_review": False, "message": None}

# Erro
{"results": [], "status": "error", "requires_manual_review": True, "message": "motivo"}

# Não encontrado
{"results": [], "status": "not_found", "requires_manual_review": True, "message": "motivo"}
```

### Como o orquestrador atual funciona (`src/search/orchestrator.py`)
```python
async def search_image(image_path: str) -> dict:
    facecheck_result, vision_result = await asyncio.gather(
        search_by_face(image_path),
        search_by_image(image_path),
        return_exceptions=True,
    )
    # tratamento de exceções...
    result = aggregate(facecheck_result, vision_result)
    result["search_time_seconds"] = round(time.monotonic() - start, 2)
    return result
```

### Como o agregador funciona (`src/search/aggregator.py`)
- `aggregate(facecheck_result, vision_result)` retorna dict com `results` (lista dedupada), `domains`, `total_raw`, `total_deduplicated`, `status`, `requires_manual_review`, `message`

### Como a UI exibe confiança (`src/ui/app.py`)
```python
def _confidence_label(item: dict) -> str:
    conf = item.get("confidence")
    if conf is None:
        return "—"
    return f"{int(conf * 100)}%"
# Linha 371: f"Fonte: {_source_label(item)} | Confiança: {_confidence_label(item)}"
```

---

## Task 1: Cliente Rekognition

**Files:**
- Criar: `src/search/rekognition_client.py`
- Testar: `tests/test_search.py` (adicionar classe `TestRekognitionClient`)

### Por que `CompareFaces` e não outras operações?

O Rekognition `CompareFaces` recebe:
- `SourceImage`: foto do cliente (o upload original)
- `TargetImage`: imagem encontrada nos resultados

E retorna a similaridade (0–100) entre os rostos. É exatamente o que precisamos: "o rosto nessa página encontrada é mesmo o do cliente?"

### Formato da chamada boto3:
```python
client.compare_faces(
    SourceImage={"Bytes": source_bytes},
    TargetImage={"Bytes": target_bytes},
    SimilarityThreshold=0,  # 0 = retorna todos os matches, mesmo os baixos
)
# Retorna: {"FaceMatches": [{"Similarity": 94.5, ...}], "UnmatchedFaces": [...]}
# Se não detectar rosto: lança InvalidParameterException
```

- [ ] **Step 1: Escrever teste que falha**

Em `tests/test_search.py`, adicionar após a classe `TestAggregator` (ou no final da Seção 1):

```python
# ─── rekognition_client ────────────────────────────────────────────────────────

class TestRekognitionClient:

    def test_returns_similarity_when_faces_match(self):
        """compare_faces retorna similarity (0–1) quando rostos são encontrados."""
        import boto3
        from unittest.mock import MagicMock, patch

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.return_value = {
            "FaceMatches": [{"Similarity": 94.5, "Face": {}}],
            "UnmatchedFaces": [],
        }

        with patch("boto3.client", return_value=mock_rekognition):
            from src.search.rekognition_client import compare_faces
            result = compare_faces(b"source_bytes", b"target_bytes")

        assert result["status"] == "found"
        assert abs(result["similarity"] - 0.945) < 0.001

    def test_returns_not_found_when_no_match(self):
        """compare_faces retorna not_found quando não há match de rosto."""
        from unittest.mock import MagicMock, patch

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.return_value = {
            "FaceMatches": [],
            "UnmatchedFaces": [{"BoundingBox": {}}],
        }

        with patch("boto3.client", return_value=mock_rekognition):
            from src.search.rekognition_client import compare_faces
            result = compare_faces(b"source_bytes", b"target_bytes")

        assert result["status"] == "not_found"
        assert result["similarity"] is None

    def test_returns_error_when_no_face_detected(self):
        """compare_faces retorna error quando Rekognition não detecta rosto."""
        from unittest.mock import MagicMock, patch
        from botocore.exceptions import ClientError

        mock_rekognition = MagicMock()
        mock_rekognition.compare_faces.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "No face detected"}},
            "CompareFaces",
        )

        with patch("boto3.client", return_value=mock_rekognition):
            from src.search.rekognition_client import compare_faces
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
```

- [ ] **Step 2: Rodar teste para confirmar que falha**

```bash
python3 -m pytest tests/test_search.py::TestRekognitionClient -v
```
Esperado: `FAILED` com `ModuleNotFoundError` ou `ImportError`

- [ ] **Step 3: Instalar boto3 e botocore**

```bash
pip install boto3 botocore
```

Adicionar ao `requirements.txt`:
```
boto3>=1.34
botocore>=1.34
```

- [ ] **Step 4: Implementar `src/search/rekognition_client.py`**

```python
"""
Cliente Amazon Rekognition — verificação de similaridade facial.

Usa CompareFaces para verificar se o rosto numa imagem encontrada
corresponde ao rosto da foto original do cliente.

Função pública:
    compare_faces(source_bytes, target_bytes) → dict
        status: "found" | "not_found" | "error"
        similarity: float (0–1) ou None
"""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
_AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")
_AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_is_configured: bool = bool(_AWS_KEY and _AWS_SECRET)


def _get_client():
    return boto3.client(
        "rekognition",
        region_name=_AWS_REGION,
        aws_access_key_id=_AWS_KEY,
        aws_secret_access_key=_AWS_SECRET,
    )


def compare_faces(source_bytes: bytes, target_bytes: bytes) -> dict:
    """
    Compara rosto da imagem-fonte com rosto da imagem-alvo.

    Args:
        source_bytes: bytes da foto do cliente (imagem de referência).
        target_bytes: bytes da imagem encontrada nos resultados.

    Returns:
        dict com:
            status     : "found" | "not_found" | "error"
            similarity : float 0–1 se found, None caso contrário
            message    : descrição do erro (apenas quando status="error")
    """
    if not _is_configured:
        return {"status": "error", "similarity": None, "message": "credenciais AWS não configuradas"}

    try:
        client = _get_client()
        response = client.compare_faces(
            SourceImage={"Bytes": source_bytes},
            TargetImage={"Bytes": target_bytes},
            SimilarityThreshold=0,
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        return {"status": "error", "similarity": None, "message": f"Rekognition {code}: {msg}"}
    except (BotoCoreError, Exception) as exc:
        return {"status": "error", "similarity": None, "message": f"Rekognition erro: {exc}"}

    matches = response.get("FaceMatches", [])
    if not matches:
        return {"status": "not_found", "similarity": None, "message": None}

    # Maior similaridade entre os matches encontrados
    best = max(matches, key=lambda m: m.get("Similarity", 0))
    similarity = round(best["Similarity"] / 100, 4)
    return {"status": "found", "similarity": similarity, "message": None}
```

- [ ] **Step 5: Rodar testes para confirmar que passam**

```bash
python3 -m pytest tests/test_search.py::TestRekognitionClient -v
```
Esperado: `4 passed`

- [ ] **Step 6: Rodar suite completa para confirmar sem regressão**

```bash
python3 -m pytest tests/ -q
```
Esperado: todos passando (mesma contagem de antes + 4 novos)

- [ ] **Step 7: Commit**

```bash
git add src/search/rekognition_client.py tests/test_search.py requirements.txt
git commit -m "feat(search): adicionar cliente Rekognition CompareFaces"
```

---

## Task 2: Enriquecimento de resultados no Aggregator

**Files:**
- Modificar: `src/search/aggregator.py` (adicionar função `enrich_with_rekognition`)
- Modificar: `src/search/orchestrator.py` (chamar enriquecimento após aggregate)
- Testar: `tests/test_search.py` (adicionar testes de enriquecimento)

### Estratégia de obtenção da imagem-alvo

Para chamar `compare_faces`, precisamos dos bytes da imagem encontrada:

| Caso | Fonte disponível | Estratégia |
|------|-----------------|------------|
| FaceCheck com thumbnail | `preview_thumbnail` = `"data:image/jpeg;base64,..."` | Decodificar base64 → bytes |
| Google Vision com image_url | `image_url` = `"https://cdn.../foto.jpg"` | Download via httpx (síncrono, timeout 5s) |
| Google Vision sem image_url | `image_url = None`, `preview_thumbnail = None` | Pular — sem imagem disponível |

**Importante:** O download de imagens pode falhar (timeout, 403, reCAPTCHA). Isso é normal — pular silenciosamente o item.

- [ ] **Step 1: Escrever testes que falham**

Em `tests/test_search.py`, adicionar após `TestRekognitionClient`:

```python
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

        with patch("src.search.aggregator.compare_faces", return_value=mock_compare):
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

        with patch("src.search.aggregator.compare_faces", side_effect=mock_compare):
            enriched = await enrich_with_rekognition(items, source_image_bytes=b"source")

        assert enriched[0].get("confidence_rekognition") is None
        assert enriched[1].get("confidence_rekognition") == 0.75
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
python3 -m pytest tests/test_search.py::TestRekognitionEnrichment -v
```
Esperado: `FAILED` com `ImportError` em `enrich_with_rekognition`

- [ ] **Step 3: Implementar `enrich_with_rekognition` em `src/search/aggregator.py`**

Adicionar ao início do arquivo (imports):
```python
import asyncio
import base64

import httpx

from .rekognition_client import compare_faces
```

Adicionar após a função `aggregate()`:
```python
_DOWNLOAD_TIMEOUT = 5.0


def _get_target_bytes(item: dict) -> bytes | None:
    """Obtém bytes da imagem-alvo: base64 thumbnail ou download via image_url."""
    thumbnail = item.get("preview_thumbnail") or ""
    if thumbnail.startswith("data:") and ";base64," in thumbnail:
        try:
            b64_part = thumbnail.split(";base64,", 1)[1]
            return base64.b64decode(b64_part)
        except Exception:
            return None

    image_url = item.get("image_url")
    if image_url:
        try:
            response = httpx.get(image_url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
            if response.status_code == 200:
                return response.content
        except Exception:
            pass

    return None


async def enrich_with_rekognition(items: list[dict], source_image_bytes: bytes) -> list[dict]:
    """
    Enriquece cada item com confidence_rekognition via Amazon Rekognition CompareFaces.

    Args:
        items: lista de resultados agregados.
        source_image_bytes: bytes da foto original do cliente.

    Returns:
        A mesma lista com confidence_rekognition adicionado onde possível.
        Itens sem imagem acessível ou com erro ficam com confidence_rekognition=None.
    """
    for item in items:
        target_bytes = await asyncio.to_thread(_get_target_bytes, item)
        if target_bytes is None:
            item["confidence_rekognition"] = None
            continue

        result = await asyncio.to_thread(compare_faces, source_image_bytes, target_bytes)
        item["confidence_rekognition"] = result.get("similarity")

    return items
```

- [ ] **Step 4: Rodar testes para confirmar que passam**

```bash
python3 -m pytest tests/test_search.py::TestRekognitionEnrichment -v
```
Esperado: `4 passed`

- [ ] **Step 5: Integrar no `src/search/orchestrator.py`**

Adicionar import:
```python
from .aggregator import aggregate, enrich_with_rekognition
from .rekognition_client import _is_configured as _rekognition_configured
```

Modificar `search_image` para incluir o passo de enriquecimento após `aggregate()`:
```python
async def search_image(image_path: str) -> dict:
    start = time.monotonic()

    facecheck_result, vision_result = await asyncio.gather(
        search_by_face(image_path),
        search_by_image(image_path),
        return_exceptions=True,
    )

    if isinstance(facecheck_result, Exception):
        facecheck_result = _exception_to_error(facecheck_result, "FaceCheck")
    if isinstance(vision_result, Exception):
        vision_result = _exception_to_error(vision_result, "GoogleVision")

    result = aggregate(facecheck_result, vision_result)

    # Enriquecer com Rekognition se credenciais configuradas
    if _rekognition_configured and result.get("results"):
        try:
            with open(image_path, "rb") as f:
                source_bytes = f.read()
            result["results"] = await enrich_with_rekognition(result["results"], source_bytes)
        except Exception:
            pass  # Rekognition é opcional — nunca bloqueia o fluxo principal

    result["search_time_seconds"] = round(time.monotonic() - start, 2)
    return result
```

- [ ] **Step 6: Rodar suite completa**

```bash
python3 -m pytest tests/ -q
```
Esperado: todos passando

- [ ] **Step 7: Commit**

```bash
git add src/search/aggregator.py src/search/orchestrator.py tests/test_search.py
git commit -m "feat(search): enriquecer resultados com Rekognition CompareFaces"
```

---

## Task 3: Exibir confidence_rekognition na UI

**Files:**
- Modificar: `src/ui/app.py` — funções `_confidence_label` e o card de resultado

### O que mudar na UI

1. `_confidence_label(item)` — mostrar Rekognition quando disponível
2. Label da fonte no card — indicar "Rekognition" quando o score vem do Rekognition

Não há testes automatizados para UI Streamlit — a verificação é visual.

- [ ] **Step 1: Atualizar `_confidence_label` em `src/ui/app.py`**

Localizar a função `_confidence_label` (linha ~85) e substituir por:

```python
def _confidence_label(item: dict) -> str:
    # Prioridade: FaceCheck confidence > Rekognition > ausente
    conf = item.get("confidence")
    reko = item.get("confidence_rekognition")

    if conf is not None:
        return f"{int(conf * 100)}% (FaceCheck)"
    if reko is not None:
        return f"{int(reko * 100)}% (Rekognition)"
    return "—"
```

- [ ] **Step 2: Atualizar `_format_confidence` em `src/export/dossie_generator.py`**

Localizar `_format_confidence` (linha ~53) e atualizar para incluir Rekognition:

```python
def _format_confidence(item: dict) -> str:
    conf = item.get("confidence")
    source = item.get("source", "")
    reko = item.get("confidence_rekognition")

    parts = []
    if conf is not None:
        label = "FaceCheck" if source == "facecheck" else "Google Vision"
        parts.append(f"{int(conf * 100)}% ({label})")
    if reko is not None:
        parts.append(f"{int(reko * 100)}% (Rekognition)")

    return " | ".join(parts) if parts else _PLACEHOLDER
```

- [ ] **Step 3: Teste manual no Streamlit**

```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib streamlit run src/ui/app.py
```

Verificar:
- [ ] Com `AWS_ACCESS_KEY_ID` configurada: resultados do Google Vision exibem score Rekognition no card
- [ ] Sem `AWS_ACCESS_KEY_ID`: comportamento igual ao atual (sem Rekognition, sem erro)
- [ ] FaceCheck mantém seu score original sem interferência

- [ ] **Step 4: Rodar suite completa**

```bash
python3 -m pytest tests/ -q
```
Esperado: todos passando

- [ ] **Step 5: Commit**

```bash
git add src/ui/app.py src/export/dossie_generator.py
git commit -m "feat(ui): exibir confidence Rekognition nos cards e no dossiê"
```

---

## Variáveis de ambiente necessárias

Adicionar ao `.env` (nunca commitar):
```env
# Amazon Rekognition — verificação de confiança facial (opcional)
AWS_ACCESS_KEY_ID=sua_chave_aqui
AWS_SECRET_ACCESS_KEY=sua_secret_aqui
AWS_REGION=us-east-1
```

Se `AWS_ACCESS_KEY_ID` não estiver configurada, o enriquecimento é simplesmente ignorado — o sistema funciona normalmente sem Rekognition.

---

## Notas sobre custo AWS Rekognition

- `CompareFaces`: **$0,001 por chamada** (1 real a cada 1.000 comparações)
- Uma busca típica retorna 10–20 resultados → custo por caso: ~$0,02
- Free tier: 5.000 chamadas/mês nos primeiros 12 meses

---

## Verificação final

```bash
python3 -m pytest tests/ -v
```
Esperado: todas as tasks anteriores + novos testes do Rekognition passando.
