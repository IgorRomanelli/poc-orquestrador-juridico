# UI Improvements: Thumbnails, Ordenação, Labels e Seções

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir exibição de thumbnails, ordenar por similaridade, sinalizar resultados sem validação facial e separar itens classificados em seção própria.

**Architecture:** Todas as mudanças estão em `src/ui/app.py`. Funções puras (sort, thumbnail resolution) são extraídas e cobertas por testes unitários. Mudanças de layout são verificadas manualmente no Streamlit.

**Tech Stack:** Python 3.14, Streamlit 1.55, pytest

---

## Mapeamento de campos por fonte (contexto crítico)

| Fonte | `image_url` | `preview_thumbnail` |
|-------|------------|-------------------|
| FaceCheck | `None` | string base64 da imagem |
| Google Vision | URL externa (pode expirar) | `None` |
| SearchAPI | link do Google (frequentemente vazio) | URL do thumbnail |

O bug de thumbnails existe porque `app.py` usa apenas `image_url` na UI — FaceCheck e SearchAPI nunca exibiram corretamente. A regressão ficou evidente após adicionar SearchAPI (mais resultados sem imagem).

---

## Estrutura de arquivos

- **Modificar:** `src/ui/app.py` — todas as 4 tarefas
- **Testar:** `tests/test_search.py` — testes unitários das funções extraídas

---

### Task 1: Corrigir exibição de thumbnails na UI e no PDF

**Problema:** UI usa `item.get("image_url")` — ignora `preview_thumbnail`. FaceCheck tem base64 em `preview_thumbnail` e `image_url=None`. SearchAPI tem URL em `preview_thumbnail` e `image_url` frequentemente vazio.

**Solução:** Extrair `_get_display_image_url(item)` que retorna `preview_thumbnail or image_url`, e usar em ambos os contextos (UI e PDF).

**Files:**
- Modify: `src/ui/app.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_search.py`, adicionar ao final:

```python
# ── Thumbnail resolution ───────────────────────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "ui"))
from app import _get_display_image_url


class TestGetDisplayImageUrl:
    def test_prefers_preview_thumbnail(self):
        item = {"preview_thumbnail": "http://thumb.jpg", "image_url": "http://full.jpg"}
        assert _get_display_image_url(item) == "http://thumb.jpg"

    def test_falls_back_to_image_url(self):
        item = {"preview_thumbnail": "", "image_url": "http://full.jpg"}
        assert _get_display_image_url(item) == "http://full.jpg"

    def test_returns_empty_when_both_empty(self):
        item = {"preview_thumbnail": "", "image_url": ""}
        assert _get_display_image_url(item) == ""

    def test_handles_none_preview_thumbnail(self):
        item = {"preview_thumbnail": None, "image_url": "http://full.jpg"}
        assert _get_display_image_url(item) == "http://full.jpg"
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd poc-orquestrador && pytest tests/test_search.py::TestGetDisplayImageUrl -v
```

Expected: FAIL com `ImportError` ou `AttributeError` — função não existe ainda.

- [ ] **Step 3: Adicionar `_get_display_image_url` em `app.py`**

Adicionar logo após `_source_label` (por volta da linha 109):

```python
def _get_display_image_url(item: dict) -> str:
    """Retorna a melhor URL de imagem disponível para exibição (thumbnail > image_url)."""
    return item.get("preview_thumbnail") or item.get("image_url") or ""
```

- [ ] **Step 4: Substituir `image_url` na UI (bloco de card, ~linha 422)**

```python
# ANTES:
img_url = item.get("image_url", "")

# DEPOIS:
img_url = _get_display_image_url(item)
```

- [ ] **Step 5: Corrigir fluxo de thumbnail no PDF (~linha 515)**

O `dossie_generator.py` só renderiza imagens cujo `preview_thumbnail` começa com `"data:"`. O fluxo atual não converte thumbnails de URL nem base64 bruto do FaceCheck. Substituir o bloco completo:

```python
# ANTES:
img_url = item_copy.get("image_url", "")
if img_url and not item_copy.get("preview_thumbnail"):
    thumbnail = _fetch_image_base64(img_url)
    if thumbnail:
        item_copy["preview_thumbnail"] = thumbnail

# DEPOIS:
thumb = item_copy.get("preview_thumbnail") or ""
img_url = item_copy.get("image_url") or ""

if thumb and not thumb.startswith("data:") and not thumb.startswith("http"):
    # FaceCheck: base64 bruto → converter para data URI
    item_copy["preview_thumbnail"] = f"data:image/jpeg;base64,{thumb}"
elif thumb and thumb.startswith("http"):
    # SearchAPI: URL do thumbnail → baixar e converter para data URI
    fetched = _fetch_image_base64(thumb)
    if fetched:
        item_copy["preview_thumbnail"] = fetched
elif img_url and img_url.startswith("http"):
    # Google Vision: image_url → baixar e converter para data URI
    fetched = _fetch_image_base64(img_url)
    if fetched:
        item_copy["preview_thumbnail"] = fetched
```

> **Por que cada caso:** `dossie_generator.py` só renderiza `thumbnail.startswith("data:")`. FaceCheck envia base64 bruto (sem prefixo `data:`), SearchAPI envia URL, Google Vision não tem thumbnail mas tem `image_url`.

- [ ] **Step 6: Rodar testes**

```bash
pytest tests/test_search.py -v
```

Expected: todos passando.

- [ ] **Step 7: Verificar na UI**

Rodar o Streamlit (`streamlit run src/ui/app.py`), fazer upload de foto e confirmar:
- Resultados FaceCheck exibem thumbnail (base64)
- Resultados SearchAPI exibem thumbnail (URL)
- Resultados Google Vision exibem imagem quando URL disponível

- [ ] **Step 8: Commit**

```bash
git add src/ui/app.py tests/test_search.py
git commit -m "fix: use preview_thumbnail as primary display image, fallback to image_url"
```

---

### Task 2: Ordenar por similaridade (maior para menor)

**Problema:** Sort atual usa `_CLASSIF_PRIORITY` → `_site_priority`. Não considera confiança — itens com 95% de match ficam misturados com itens sem score.

**Solução:** Extrair `_sort_results(results, classifs)` com chave: classificação → confiança descendente (None no final) → prioridade de site.

**Files:**
- Modify: `src/ui/app.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
# ── Sort ───────────────────────────────────────────────────────────────────────
# Nota: o sys.path para "src/ui" já foi inserido pelo bloco TestGetDisplayImageUrl acima.
# Se rodar este teste isoladamente, adicione:
#   import sys, os
#   sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "ui"))

from app import _sort_results


class TestSortResults:
    def _classifs(self, items, status="pendente"):
        return {i["page_url"]: status for i in items}

    def test_sorts_by_confidence_descending(self):
        items = [
            {"page_url": "a", "confidence": 0.5, "confidence_rekognition": None, "domain": "x.com"},
            {"page_url": "b", "confidence": 0.9, "confidence_rekognition": None, "domain": "y.com"},
            {"page_url": "c", "confidence": 0.7, "confidence_rekognition": None, "domain": "z.com"},
        ]
        classifs = self._classifs(items)
        sorted_items = _sort_results(items, classifs)
        assert [i["page_url"] for i in sorted_items] == ["b", "c", "a"]

    def test_none_confidence_goes_last(self):
        items = [
            {"page_url": "a", "confidence": None, "confidence_rekognition": None, "domain": "x.com"},
            {"page_url": "b", "confidence": 0.8, "confidence_rekognition": None, "domain": "y.com"},
        ]
        classifs = self._classifs(items)
        sorted_items = _sort_results(items, classifs)
        assert sorted_items[0]["page_url"] == "b"
        assert sorted_items[1]["page_url"] == "a"

    def test_uses_rekognition_confidence_when_no_facecheck(self):
        items = [
            {"page_url": "a", "confidence": None, "confidence_rekognition": 0.6, "domain": "x.com"},
            {"page_url": "b", "confidence": None, "confidence_rekognition": 0.9, "domain": "y.com"},
        ]
        classifs = self._classifs(items)
        sorted_items = _sort_results(items, classifs)
        assert sorted_items[0]["page_url"] == "b"
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
pytest tests/test_search.py::TestSortResults -v
```

Expected: FAIL com `ImportError`.

- [ ] **Step 3: Implementar `_sort_results` em `app.py`**

Adicionar logo após `_get_display_image_url`:

```python
def _sort_results(results: list, classifs: dict) -> list:
    """Ordena resultados: classificação → confiança desc (None no final) → tipo de site."""
    def _key(r):
        url = r.get("page_url", "")
        classif = _CLASSIF_PRIORITY.get(classifs.get(url, "pendente"), 0)
        conf = r.get("confidence") if r.get("confidence") is not None else r.get("confidence_rekognition")
        conf_key = -conf if conf is not None else 1.0  # None vai para o final
        return (classif, conf_key, _site_priority(r))
    return sorted(results, key=_key)
```

- [ ] **Step 4: Substituir o bloco de sort na UI (~linha 386)**

```python
# ANTES:
filtered_results = sorted(
    filtered_results,
    key=lambda r: (
        _CLASSIF_PRIORITY.get(classifs.get(r.get("page_url", ""), "pendente"), 0),
        _site_priority(r),
    ),
)

# DEPOIS:
filtered_results = _sort_results(filtered_results, classifs)
```

- [ ] **Step 5: Rodar testes**

```bash
pytest tests/test_search.py -v
```

Expected: todos passando.

- [ ] **Step 6: Verificar na UI**

Confirmar que resultados com 90%+ aparecem antes de resultados com 50% e antes dos sem score.

- [ ] **Step 7: Commit**

```bash
git add src/ui/app.py tests/test_search.py
git commit -m "feat: sort results by confidence descending, None last"
```

---

### Task 3: Sinalizar resultados sem validação facial (Opção A)

**Problema:** Itens com `confidence=None` e `confidence_rekognition=None` exibem "—", o que não comunica nada ao advogado. Ele não sabe se é um resultado incerto ou simplesmente sem dado.

**Solução:** Mudar o label de "—" para "⚠️ Sem validação facial" em `_confidence_label`. Manter o checkbox "Sem confiança" existente para controle de visibilidade.

**Files:**
- Modify: `src/ui/app.py` (função `_confidence_label`)

- [ ] **Step 1: Atualizar `_confidence_label`**

```python
# ANTES:
def _confidence_label(item: dict) -> str:
    conf = item.get("confidence")
    reko = item.get("confidence_rekognition")
    if conf is not None:
        return f"{int(conf * 100)}% (FaceCheck)"
    if reko is not None:
        return f"{int(reko * 100)}% (Rekognition)"
    return "—"

# DEPOIS:
def _confidence_label(item: dict) -> str:
    conf = item.get("confidence")
    reko = item.get("confidence_rekognition")
    if conf is not None:
        return f"{int(conf * 100)}% (FaceCheck)"
    if reko is not None:
        return f"{int(reko * 100)}% (Rekognition)"
    return "⚠️ Sem validação facial"
```

- [ ] **Step 2: Verificar na UI**

Confirmar que itens do Google Vision e SearchAPI sem score mostram "⚠️ Sem validação facial" ao lado de "Fonte".

- [ ] **Step 3: Commit**

```bash
git add src/ui/app.py
git commit -m "feat: label items without confidence as 'sem validação facial'"
```

---

### Task 4: Separar itens classificados em seção própria

> ⚠️ **Dependência:** Esta task usa `_get_display_image_url` (Task 1) e `_sort_results` (Task 2). Execute as tasks em ordem 1 → 2 → 3 → 4.

**Problema:** Itens classificados como Violação/Investigar ficam no final da lista misturados com pendentes. O advogado perde o contexto do que já avaliou.

**Solução:** Extrair `_render_result_card` como função de módulo (fora do bloco condicional) e dividir a lista em três seções:
- **Classificados** (violação + investigar) — topo
- **Pendentes** — meio
- **Descartados** (não é violação) — colapsado no final (expander fechado por padrão)

`nao_violacao` vai para um expander colapsado — o advogado pode revisar se precisar, mas não polui a lista principal.

**Files:**
- Modify: `src/ui/app.py` (bloco de renderização de resultados)

- [ ] **Step 1: Mover `_render_result_card` para escopo de módulo**

Adicionar a função **antes** do bloco `st.set_page_config(...)` (~linha 72), fora de qualquer `if`. Isso garante que seja testável e não seja redefinida a cada rerun.

Inserir após a linha `_CLASSIF_PRIORITY = {"pendente": 0, "violacao": 1, "investigar": 2, "nao_violacao": 3}` (~linha 67):, adicionar a função:

```python
def _render_result_card(item: dict, classifs: dict) -> None:
    url = item.get("page_url", "")
    domain = item.get("domain", "—")
    classification = classifs.get(url, "pendente")
    border_color = {
        "violacao": "#e74c3c",
        "investigar": "#f39c12",
        "nao_violacao": "#27ae60",
        "pendente": "#bdc3c7",
    }.get(classification, "#bdc3c7")

    with st.container():
        st.markdown(
            f'<div style="border-left: 4px solid {border_color}; padding-left: 12px; margin-bottom: 8px;">',
            unsafe_allow_html=True,
        )
        col_thumb, col_info, col_btns = st.columns([1, 2.5, 2])

        with col_thumb:
            img_url = _get_display_image_url(item)
            if img_url:
                try:
                    st.image(img_url, width=110)
                except Exception:
                    st.caption("🖼️")
            else:
                st.caption("—")

        with col_info:
            st.markdown(f"**Domínio:** {domain}")
            st.markdown(
                f"**URL:** [{url[:80]}...]({url})" if len(url) > 80 else f"**URL:** [{url}]({url})"
            )
            st.caption(f"Fonte: {_source_label(item)} | Confiança: {_confidence_label(item)}")

        with col_btns:
            btn_cols = st.columns(3)
            with btn_cols[0]:
                active = classification == "violacao"
                if st.button("✅ Violação", key=f"v_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "violacao")
                    st.rerun()
            with btn_cols[1]:
                active = classification == "nao_violacao"
                if st.button("❌ Não é", key=f"n_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "nao_violacao")
                    st.rerun()
            with btn_cols[2]:
                active = classification == "investigar"
                if st.button("🔍 Investigar", key=f"i_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "investigar")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
```

- [ ] **Step 2: Substituir o loop de renderização**

Substituir o bloco `for item in filtered_results:` (até o final do loop) por:

```python
classified = [
    r for r in filtered_results
    if classifs.get(r.get("page_url", ""), "pendente") in ("violacao", "investigar")
]
pending = [
    r for r in filtered_results
    if classifs.get(r.get("page_url", ""), "pendente") == "pendente"
]
discarded = [
    r for r in filtered_results
    if classifs.get(r.get("page_url", ""), "pendente") == "nao_violacao"
]

if classified:
    st.markdown(f"#### ✅ Classificados ({len(classified)})")
    for item in classified:
        _render_result_card(item, classifs)
    st.markdown("---")

if pending:
    st.markdown(f"#### ⏳ Pendentes ({len(pending)})")
    for item in pending:
        _render_result_card(item, classifs)

if discarded:
    with st.expander(f"Descartados ({len(discarded)})", expanded=False):
        for item in discarded:
            _render_result_card(item, classifs)
```

- [ ] **Step 3: Verificar na UI**

- Classificar 2–3 itens como Violação ou Investigar → confirmar que sobem para "Classificados"
- Confirmar que "Pendentes" mostra apenas os não classificados
- Marcar 1 item como "Não é" → confirmar que some da lista principal e apareça no expander "Descartados" colapsado

- [ ] **Step 4: Commit**

```bash
git add src/ui/app.py
git commit -m "feat: split results into classified and pending sections"
```

---

---

### Task 5: Exibir CEP no relatório/dossiê

**Causa raiz — dois bugs independentes:**

1. `_lookup_receitaws` hardcoda `"cep": None` (linha 203 de `cnpj_client.py`) — a API retorna o CEP mas o código não extrai. Quando BrasilAPI falha e o fallback é acionado, CEP some.

2. `dossie_generator.py` (linha 119) usa condição `cep != _PLACEHOLDER and municipio` — mas `municipio` é sempre `""` porque ambas as APIs (BrasilAPI e receitaws) já embutem município dentro do campo `logradouro` via `_build_address`. A condição é impossível de satisfazer.

**Solução:**
- Em `cnpj_client.py`: extrair `cep` do response receitaws (`data.get("cep")`)
- Em `dossie_generator.py`: remover a exigência de `municipio` na condição do CEP

**Files:**
- Modify: `src/lookup/cnpj_client.py` (linha 203)
- Modify: `src/export/dossie_generator.py` (linha 119)
- Test: `tests/test_search.py`

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_search.py`, adicionar:

```python
# ── CNPJ CEP ──────────────────────────────────────────────────────────────────

import pytest
from unittest.mock import patch, AsyncMock
from src.lookup.cnpj_client import _lookup_receitaws


class TestReceitawsCep:
    @pytest.mark.asyncio
    async def test_receitaws_returns_cep(self):
        mock_response = {
            "nome": "Empresa Teste",
            "fantasia": "",
            "situacao": "ATIVA",
            "atividade_principal": [{"text": "Comércio"}],
            "qsa": [],
            "logradouro": "Rua Teste",
            "numero": "100",
            "complemento": "",
            "municipio": "São Paulo",
            "uf": "SP",
            "cep": "01310-100",
        }
        with patch("src.lookup.cnpj_client.httpx.AsyncClient") as mock_client:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            result = await _lookup_receitaws("12345678000195", "12.345.678/0001-95")

        assert result["cep"] == "01310-100"
        assert result["status"] == "found"
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
pytest tests/test_search.py::TestReceitawsCep -v
```

Expected: FAIL — `result["cep"]` é `None` em vez de `"01310-100"`.

- [ ] **Step 3: Corrigir `_lookup_receitaws` em `cnpj_client.py`**

Na função `_lookup_receitaws` (~linha 203), substituir:

```python
# ANTES:
"cep": None,

# DEPOIS:
"cep": str(data["cep"]).strip() if data.get("cep") else None,
```

- [ ] **Step 4: Corrigir condição em `dossie_generator.py`**

Na função `_render_item` (~linha 119), substituir:

```python
# ANTES:
if cep != _PLACEHOLDER and municipio:
    endereco = f"{endereco} — CEP {cep}"

# DEPOIS:
if cep != _PLACEHOLDER:
    endereco = f"{endereco} — CEP {cep}"
```

> **Motivo:** `municipio` é sempre `""` porque BrasilAPI e receitaws já embitem município em `logradouro` via `_build_address`. A condição bloqueava o CEP mesmo quando ele estava disponível.

- [ ] **Step 5: Rodar testes**

```bash
pytest tests/test_search.py -v
```

Expected: todos passando.

- [ ] **Step 6: Verificar no dossiê**

- Gerar um dossiê com ao menos um domínio com CNPJ encontrado
- Confirmar que o campo **Endereço** inclui `— CEP XXXXX` no final
- Testar tanto com BrasilAPI quanto forçando o fallback receitaws (pode simular desconectando a rede brevemente)

- [ ] **Step 7: Commit**

```bash
git add src/lookup/cnpj_client.py src/export/dossie_generator.py tests/test_search.py
git commit -m "fix: extract CEP from receitaws response and fix CEP condition in dossie"
```

---

## Verificação final

```bash
pytest tests/test_search.py -v
streamlit run src/ui/app.py
```

Checar:
- [ ] Thumbnails aparecem para FaceCheck, SearchAPI e Google Vision
- [ ] Resultados ordenados por confiança (maior primeiro)
- [ ] Itens sem score mostram "⚠️ Sem validação facial"
- [ ] Seção "Classificados" aparece acima de "Pendentes" após classificar
- [ ] CEP aparece no endereço do dossiê quando CNPJ é encontrado
