# Melhorias UI e Dossiê — POC Orquestrador

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Melhorar a experiência de auditoria no Streamlit e a qualidade do dossiê PDF com identidade visual Goulart|Law, campos completos do CNPJ, imagens embutidas, e filtros de relevância.

**Architecture:** Todas as mudanças são incrementais e isoladas por arquivo. As tarefas de UI modificam apenas `app.py`. As tarefas de dossiê modificam `dossie_generator.py` e `pdf_exporter.py`. Não há mudanças de interface pública entre módulos — apenas adição de campos e lógica de apresentação.

**Tech Stack:** Python 3.14, Streamlit ≥1.32, WeasyPrint ≥62, httpx, markdown, pytest

---

## Mapa de arquivos

| Arquivo | Tarefas | Ação |
|---------|---------|------|
| `src/ui/app.py` | 1, 6, 2, 3, 4 | Modificar |
| `src/export/pdf_exporter.py` | 5 | Modificar |
| `src/export/dossie_generator.py` | 7, 8 | Modificar |
| `src/export/assets/logo_goulart_law.png` | 5 | Já extraído |
| `tests/test_export.py` | 7, 8 | Modificar |

---

## Task 1: Thumbnails nos cards de resultado (Streamlit)

**Files:**
- Modify: `src/ui/app.py` — loop de resultados (~linha 208)

Adicionar coluna de thumbnail à esquerda de cada card de resultado. O campo `image_url` já existe em cada item do resultado de busca.

- [ ] **Step 1: Localizar o loop de resultados em app.py**

Abrir `src/ui/app.py`. O loop de resultados começa em torno da linha 208:
```python
for item in filtered_results:
```
A linha relevante de layout é:
```python
col_info, col_btns = st.columns([3, 2])
```

- [ ] **Step 2: Adicionar coluna de thumbnail ao layout**

Substituir a linha de colunas e o bloco `with col_info:` pelo seguinte:

```python
col_thumb, col_info, col_btns = st.columns([1, 2.5, 2])

with col_thumb:
    img_url = item.get("image_url", "")
    if img_url:
        try:
            st.image(img_url, width=110, use_container_width=False)
        except Exception:
            st.caption("🖼️")
    else:
        st.caption("—")
```

O bloco `with col_info:` e `with col_btns:` permanecem sem alteração.

- [ ] **Step 3: Testar manualmente**

```bash
cd poc-orquestrador
streamlit run src/ui/app.py
```

Carregar uma imagem, clicar em Buscar. Verificar que cada card exibe um thumbnail à esquerda. Alguns podem mostrar "🖼️" se a URL não for acessível publicamente — isso é esperado.

- [ ] **Step 4: Commit**

```bash
git add src/ui/app.py
git commit -m "feat(ui): adicionar thumbnails nos cards de resultado"
```

---

## Task 5: Identidade visual Goulart|Law no PDF

**Files:**
- Modify: `src/export/pdf_exporter.py`
- Already created: `src/export/assets/logo_goulart_law.png`

Substituir o CSS genérico pelo visual Goulart|Law: logo no header, cores da marca (vermelho `#C00000`, azul `#1A3566`), fonte serif Garamond, rodapé com nome do escritório.

- [ ] **Step 1: Escrever teste que verifica presença do logo no HTML gerado**

Em `tests/test_export.py`, adicionar:

```python
def test_html_contains_logo():
    """PDF HTML deve conter o logo do escritório como base64."""
    from src.export.pdf_exporter import _to_html
    html = _to_html("# Teste")
    assert "data:image/png;base64," in html, "HTML deve conter logo base64"
    assert "logo_goulart_law" not in html, "Não deve vazar path do arquivo"


def test_html_contains_brand_colors():
    """CSS deve usar as cores da marca Goulart|Law."""
    from src.export.pdf_exporter import _CSS
    assert "#C00000" in _CSS, "Vermelho primário ausente"
    assert "#1A3566" in _CSS, "Azul primário ausente"


def test_html_contains_footer_text():
    """Rodapé deve mencionar Goulart|Law."""
    from src.export.pdf_exporter import _to_html
    html = _to_html("# Teste")
    assert "Goulart" in html
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd poc-orquestrador
python -m pytest tests/test_export.py::test_html_contains_logo tests/test_export.py::test_html_contains_brand_colors tests/test_export.py::test_html_contains_footer_text -v
```

Esperado: 3 FAILED.

- [ ] **Step 3: Implementar identidade visual em pdf_exporter.py**

Substituir o conteúdo completo de `src/export/pdf_exporter.py` por:

```python
"""
Exportador de PDF: converte markdown em HTML e depois em PDF via WeasyPrint.
Identidade visual: Goulart|Law — Advocacia Especializada.

Duas funções públicas:
    export(markdown_text, output_path) → salva PDF em disco, retorna output_path
    to_bytes(markdown_text)            → retorna bytes do PDF (para st.download_button)
"""

import base64
import os

import markdown as _md

# ─── assets ───────────────────────────────────────────────────────────────────

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _load_logo_b64() -> str:
    """Carrega logo como base64. Retorna string vazia se arquivo não encontrado."""
    logo_path = os.path.join(_ASSETS_DIR, "logo_goulart_law.png")
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""


_LOGO_B64 = _load_logo_b64()

# ─── CSS — identidade visual Goulart|Law ──────────────────────────────────────

_CSS = """
@page {
    margin: 2.5cm 2cm 3cm 2cm;
    @bottom-center {
        content: "Goulart|Law · Advocacia Especializada  —  " counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #888;
        font-family: "Garamond", Georgia, serif;
    }
}

body {
    font-family: "Garamond", Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.7;
    color: #1a1a1a;
}

.doc-header {
    text-align: left;
    margin-bottom: 1.2em;
    padding-bottom: 0.8em;
    border-bottom: 2px solid #C00000;
}

.doc-header img {
    height: 52px;
}

h1 {
    font-size: 17pt;
    color: #C00000;
    margin-bottom: 0.2em;
    margin-top: 0.6em;
    border-bottom: none;
    padding-bottom: 0;
}

h2 {
    font-size: 12pt;
    color: #1A3566;
    margin-top: 1.6em;
    margin-bottom: 0.4em;
    border-bottom: 1px solid #1A3566;
    padding-bottom: 0.15em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

h3 {
    font-size: 11pt;
    color: #C00000;
    margin-top: 1.2em;
    margin-bottom: 0.3em;
}

p {
    margin: 0.3em 0 0.5em 0;
}

ul, ol {
    margin: 0.3em 0 0.6em 1.4em;
}

li {
    margin-bottom: 0.2em;
}

strong {
    font-weight: bold;
    color: #1a1a1a;
}

em {
    font-style: italic;
    color: #555;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 1.2em 0;
}

a {
    color: #1A3566;
    word-break: break-all;
}

img {
    max-width: 240px;
    max-height: 240px;
    border: 1px solid #ccc;
    margin: 6px 0;
    display: block;
}
"""

# ─── funções internas ──────────────────────────────────────────────────────────


def _to_html(markdown_text: str) -> str:
    body = _md.markdown(markdown_text, extensions=["extra"])
    logo_tag = (
        f'<img src="data:image/png;base64,{_LOGO_B64}" alt="Goulart|Law">'
        if _LOGO_B64
        else "<strong>Goulart|Law · Advocacia Especializada</strong>"
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>{_CSS}</style>
</head>
<body>
<div class="doc-header">
  {logo_tag}
</div>
{body}
</body>
</html>"""


# ─── funções públicas ──────────────────────────────────────────────────────────


def export(markdown_text: str, output_path: str) -> str:
    """
    Converte markdown em PDF e salva em output_path.

    Raises:
        RuntimeError: se a geração ou escrita do PDF falhar.
    """
    from weasyprint import HTML

    html = _to_html(markdown_text)
    try:
        HTML(string=html).write_pdf(output_path)
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF em '{output_path}': {exc}") from exc
    return output_path


def to_bytes(markdown_text: str) -> bytes:
    """
    Converte markdown em PDF e retorna como bytes.
    Usado para st.download_button no Streamlit.

    Raises:
        RuntimeError: se a geração do PDF falhar.
    """
    from weasyprint import HTML

    html = _to_html(markdown_text)
    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
```

- [ ] **Step 4: Rodar testes**

```bash
python -m pytest tests/test_export.py::test_html_contains_logo tests/test_export.py::test_html_contains_brand_colors tests/test_export.py::test_html_contains_footer_text -v
```

Esperado: 3 PASSED.

- [ ] **Step 5: Rodar suite completa para garantir sem regressão**

```bash
python -m pytest tests/test_export.py -v
```

Esperado: todos PASSED.

- [ ] **Step 6: Commit**

> **Nota CI:** o arquivo `src/export/assets/logo_goulart_law.png` precisa estar commitado para que o teste `test_html_contains_logo` passe em qualquer ambiente. Verificar que o `.gitignore` não exclui arquivos `.png` dentro de `src/`.

```bash
git add src/export/pdf_exporter.py src/export/assets/logo_goulart_law.png
git commit -m "feat(pdf): identidade visual Goulart|Law — logo, cores e rodapé"
```

---

## Task 7: Campos faltantes no dossiê

**Files:**
- Modify: `src/export/dossie_generator.py` — função `_render_item`
- Modify: `tests/test_export.py`

Os seguintes campos existem no `cnpj_data` retornado pelo `cnpj_client.py` mas não aparecem no dossiê:
`nome_fantasia`, `atividade_principal`, `telefone`, `email`, `cep`, `natureza_juridica`, `capital_social`, `fonte`.

- [ ] **Step 1: Escrever testes para campos faltantes**

Em `tests/test_export.py`, adicionar (ou num bloco separado):

```python
def _make_full_item(cnpj_extra: dict = None) -> dict:
    """Helper: cria item completo para TestDossieGeneratorCamposCompletos."""
    cnpj_data = {
        "cnpj": "12.345.678/0001-90",
        "razao_social": "Empresa Teste SA",
        "nome_fantasia": "Marca Teste",
        "situacao": "ATIVA",
        "atividade_principal": "Comércio varejista de roupas",
        "logradouro": "Rua A, 123, Centro, São Paulo, SP",
        "socios": ["Ana Silva — Sócia"],
        "telefone": "11999990000",
        "email": "contato@empresa.com",
        "cep": "01234-567",
        "natureza_juridica": "Sociedade Limitada",
        "capital_social": 50000.0,
        "fonte": "brasilapi",
        "status": "found",
    }
    if cnpj_extra:
        cnpj_data.update(cnpj_extra)
    return {
        "search_result": {
            "page_url": "https://empresa.com/foto",
            "domain": "empresa.com",
            "source": "facecheck",
            "confidence": 0.87,
        },
        "lookup": {"cnpj_data": cnpj_data, "whois": {}, "jucesp": {}, "summary": {}},
    }


class TestDossieGeneratorCamposCompletos:
    def test_nome_fantasia_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "Marca Teste" in md

    def test_atividade_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "Comércio varejista de roupas" in md

    def test_telefone_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "11999990000" in md

    def test_email_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "contato@empresa.com" in md

    def test_cep_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "01234-567" in md

    def test_natureza_juridica_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "Sociedade Limitada" in md

    def test_capital_social_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "50000" in md

    def test_fonte_api_presente(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "brasilapi" in md

    def test_campos_ausentes_exibem_placeholder(self):
        """Campos None devem mostrar placeholder, nunca ser omitidos."""
        from src.export.dossie_generator import _render_item
        item = _make_full_item({"nome_fantasia": None, "telefone": None, "email": None})
        md = _render_item(1, item)
        assert md.count("— não identificado") >= 3
```

- [ ] **Step 2: Rodar para confirmar que falham**

```bash
python -m pytest tests/test_export.py::TestDossieGeneratorCamposCompletos -v
```

Esperado: todos FAILED (campos ainda não estão no markdown gerado).

- [ ] **Step 3: Atualizar `_render_item` em dossie_generator.py**

Localizar a função `_render_item` (~linha 67). Adicionar extração dos novos campos após a linha `confidence = _format_confidence(search)`:

```python
# Campos adicionais do CNPJ
nome_fantasia = _v(cnpj_data.get("nome_fantasia"))
atividade = _v(cnpj_data.get("atividade_principal"))
telefone = _v(cnpj_data.get("telefone"))
email_cnpj = _v(cnpj_data.get("email"))
cep = _v(cnpj_data.get("cep"))
natureza_juridica = _v(cnpj_data.get("natureza_juridica"))
capital_social_raw = cnpj_data.get("capital_social")
capital_social = (
    f"R$ {capital_social_raw:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(capital_social_raw, (int, float))
    else _PLACEHOLDER
)
fonte_api = _v(cnpj_data.get("fonte"))
```

E substituir o bloco `return (...)` para incluir os novos campos após `"- **Empresa responsável:**"`:

```python
return (
    f"### {label} {index}\n"
    f"{image_block}"
    f"- **URL:** {page_url}\n"
    f"- **Domínio:** {domain}\n"
    f"- **Empresa responsável:** {razao_social}\n"
    f"- **Nome fantasia:** {nome_fantasia}\n"
    f"- **CNPJ:** {cnpj}\n"
    f"- **Atividade:** {atividade}\n"
    f"- **Responsável (sócios):** {socios}\n"
    f"- **Situação:** {situacao}\n"
    f"- **Natureza jurídica:** {natureza_juridica}\n"
    f"- **Capital social:** {capital_social}\n"
    f"- **Endereço:** {endereco}\n"
    f"- **CEP:** {cep}\n"
    f"- **Telefone:** {telefone}\n"
    f"- **E-mail:** {email_cnpj}\n"
    f"- **WHOIS:** {whois_dates}\n"
    f"- **Registrante WHOIS:** {registrant}\n"
    f"- **JUCESP:** {jucesp_url}\n"
    f"- **Confiança da busca:** {confidence}\n"
    f"- **Fonte da API:** {fonte_api}\n"
)
```

- [ ] **Step 4: Rodar testes**

```bash
python -m pytest tests/test_export.py::TestDossieGeneratorCamposCompletos -v
```

Esperado: todos PASSED.

- [ ] **Step 5: Rodar suite completa**

```bash
python -m pytest tests/ -v --ignore=tests/test_lookup.py -k "not real_domain and not real_image"
```

Esperado: todos PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/export/dossie_generator.py tests/test_export.py
git commit -m "feat(dossie): adicionar campos completos do CNPJ ao dossiê"
```

---

## Task 8: Google Maps no dossiê

**Files:**
- Modify: `src/export/dossie_generator.py`
- Modify: `tests/test_export.py`

Adicionar link direto para o Google Maps do endereço da empresa, gerado a partir do `logradouro` + `cep` já disponíveis no `cnpj_data`.

- [ ] **Step 1: Escrever teste**

Em `tests/test_export.py`, adicionar:

```python
class TestDossieGeneratorGoogleMaps:
    def test_maps_link_presente_quando_ha_endereco(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        assert "maps.google.com" in md

    def test_maps_link_ausente_quando_sem_endereco(self):
        from src.export.dossie_generator import _render_item
        item = _make_full_item({"logradouro": None, "cep": None})
        # Mesmo sem endereço, a linha do maps deve aparecer com placeholder
        md = _render_item(1, item)
        assert "**Google Maps:**" in md

    def test_maps_url_contem_endereco_codificado(self):
        from src.export.dossie_generator import _render_item
        md = _render_item(1, _make_full_item())
        # O endereço "Rua A, 123, Centro, São Paulo, SP" deve estar na URL
        assert "maps.google.com/?q=" in md
```

- [ ] **Step 2: Rodar para confirmar que falham**

```bash
python -m pytest tests/test_export.py::TestDossieGeneratorGoogleMaps -v
```

Esperado: 3 FAILED.

- [ ] **Step 3: Adicionar import e helper `_maps_url` em dossie_generator.py**

No topo de `src/export/dossie_generator.py`, adicionar import:

```python
from urllib.parse import quote_plus as _quote_plus
```

Após os helpers existentes, adicionar:

```python
def _maps_url(logradouro: str, cep: str = "") -> str:
    """Gera URL do Google Maps para o endereço. Retorna placeholder se sem dados."""
    parts = [p for p in [logradouro, cep] if p and p != _PLACEHOLDER]
    if not parts:
        return _PLACEHOLDER
    query = _quote_plus(", ".join(parts))
    return f"https://maps.google.com/?q={query}"
```

- [ ] **Step 4: Usar `_maps_url` em `_render_item`**

Na função `_render_item`, após a linha `cep = _v(cnpj_data.get("cep"))`, adicionar:

```python
maps_link = _maps_url(endereco, cep)
```

E no bloco `return (...)`, após a linha `f"- **CEP:** {cep}\n"`, adicionar:

```python
f"- **Google Maps:** {maps_link}\n"
```

- [ ] **Step 5: Rodar testes**

```bash
python -m pytest tests/test_export.py::TestDossieGeneratorGoogleMaps -v
```

Esperado: 3 PASSED.

- [ ] **Step 6: Rodar suite completa**

```bash
python -m pytest tests/ -v --ignore=tests/test_lookup.py -k "not real_domain and not real_image"
```

- [ ] **Step 7: Commit**

```bash
git add src/export/dossie_generator.py tests/test_export.py
git commit -m "feat(dossie): adicionar link Google Maps do endereço da empresa"
```

---

## Task 6: Imagens das violações embutidas no PDF

**Files:**
- Modify: `src/ui/app.py`

> **Ordem de execução:** esta task deve ser executada **antes da Task 2**, pois o helper `_fetch_image_base64` é inserido após `_passes_filter`. A Task 2 modifica a assinatura de `_passes_filter` mas não remove a função — a âncora de inserção continua válida. A ordem do mapa de arquivos (1, 6, 2, 3, 4) reflete a sequência correta.

Quando o advogado gera o dossiê PDF, buscar cada `image_url` dos resultados marcados, convertê-la para base64, e passá-la como `preview_thumbnail` para o `dossie_generator`. O generator já sabe renderizar esse campo — só precisamos alimentá-lo.

- [ ] **Step 1: Adicionar imports em app.py**

No topo de `src/ui/app.py`, adicionar:

```python
import base64
```

O `httpx` já é uma dependência do projeto (usado pelos clients de busca).

- [ ] **Step 2: Adicionar helper `_fetch_image_base64`**

Após a função `_passes_filter`, adicionar:

```python
def _fetch_image_base64(url: str) -> str | None:
    """
    Baixa imagem de uma URL e retorna como data URL base64.
    Retorna None se a URL não for acessível ou não for uma imagem.
    Timeout de 8s para não travar a geração do dossiê.
    """
    if not url:
        return None
    try:
        import httpx
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return None
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return None
```

- [ ] **Step 3: Buscar thumbnails ao gerar o dossiê**

No bloco de geração do dossiê (dentro do `with st.spinner("Gerando dossiê...")`), substituir o loop que constrói `violations_data` e `investigate_data` pelo seguinte:

```python
with st.spinner("Gerando dossiê (buscando imagens)..."):
    violations_data = []
    investigate_data = []

    for item in marked_items:
        domain = item.get("domain", "")
        item_copy = dict(item)

        # Tentar embutir imagem para o PDF
        img_url = item_copy.get("image_url", "")
        if img_url and not item_copy.get("preview_thumbnail"):
            thumbnail = _fetch_image_base64(img_url)
            if thumbnail:
                item_copy["preview_thumbnail"] = thumbnail

        enriched = {
            "search_result": item_copy,
            "lookup": domain_lookup.get(domain, {}),
        }
        label = classifs.get(item.get("page_url", ""))
        if label == "violacao":
            violations_data.append(enriched)
        else:
            investigate_data.append(enriched)
```

- [ ] **Step 4: Testar manualmente**

```bash
streamlit run src/ui/app.py
```

Subir uma imagem, buscar, marcar uma violação, gerar PDF. Abrir o PDF e verificar que a imagem da violação aparece embutida no documento.

- [ ] **Step 5: Commit**

```bash
git add src/ui/app.py
git commit -m "feat(pdf): embutir imagens das violações no dossiê PDF"
```

---

## Task 2: Filtro de redes sociais

**Files:**
- Modify: `src/ui/app.py`

Adicionar opção para ocultar resultados de redes sociais (Instagram, Facebook, TikTok etc.), ativado por padrão, já que o interesse do Ulysses é em sites e Google Maps.

- [ ] **Step 1: Adicionar lista de domínios de redes sociais e helper**

Em `src/ui/app.py`, após as constantes no topo (após `load_dotenv()`), adicionar:

```python
_SOCIAL_DOMAINS = frozenset({
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "pinterest.com", "linkedin.com",
    "reddit.com", "snapchat.com", "tumblr.com", "flickr.com",
    "threads.net", "vk.com", "t.me",
})


def _is_social(item: dict) -> bool:
    """Retorna True se o domínio pertence a uma rede social conhecida."""
    domain = item.get("domain", "").lower()
    return any(social in domain for social in _SOCIAL_DOMAINS)
```

- [ ] **Step 2: Adicionar checkbox no painel de filtros**

Na seção de filtros (dentro do `with st.expander("Filtros")`), adicionar uma quarta coluna após `fcol3`:

```python
fcol1, fcol2, fcol3, fcol4 = st.columns([2, 3, 1, 1])
# ... (fcol1, fcol2, fcol3 permanecem iguais)
with fcol4:
    hide_social = st.checkbox(
        "Ocultar redes sociais",
        value=True,
        help="Remove Instagram, Facebook, TikTok etc. — foca em sites e Google Maps.",
    )
```

- [ ] **Step 3: Atualizar `_passes_filter` para aceitar o novo parâmetro**

Substituir a assinatura e corpo de `_passes_filter`:

```python
def _passes_filter(
    item: dict,
    filter_sources: list,
    conf_min: float,
    conf_max: float,
    include_no_conf: bool,
    hide_social: bool = False,
) -> bool:
    if item.get("source") not in filter_sources:
        return False
    if hide_social and _is_social(item):
        return False
    conf = item.get("confidence")
    if conf is None:
        return include_no_conf
    return conf_min <= conf <= conf_max
```

- [ ] **Step 4: Passar `hide_social` na chamada de `_passes_filter`**

Localizar a list comprehension `filtered_results = [...]` e adicionar o parâmetro:

```python
filtered_results = [
    r for r in results
    if _passes_filter(r, filter_sources, conf_min, conf_max, include_no_conf, hide_social)
]
```

- [ ] **Step 5: Testar manualmente**

Rodar o app, buscar uma imagem que retorne resultados de redes sociais. Verificar que com "Ocultar redes sociais" marcado (default), resultados de instagram.com etc. não aparecem. Desmarcando, eles reaparecem.

- [ ] **Step 6: Commit**

```bash
git add src/ui/app.py
git commit -m "feat(ui): filtro para ocultar redes sociais dos resultados"
```

---

## Task 3: Ordenação por tipo de site

**Files:**
- Modify: `src/ui/app.py`

Ordenar os resultados filtrados: itens pendentes primeiro (mais acionáveis), depois por tipo de site (sites comerciais → blogs → redes sociais).

- [ ] **Step 1: Adicionar helper de prioridade de site**

Em `src/ui/app.py`, após a função `_is_social`, adicionar:

```python
def _site_priority(item: dict) -> int:
    """
    Prioridade de ordenação por tipo de site.
    0 = site comercial / Google Maps (maior relevância jurídica)
    1 = rede social (menor relevância)
    """
    return 1 if _is_social(item) else 0
```

- [ ] **Step 2: Definir prioridade de classificação**

Logo abaixo, adicionar:

```python
_CLASSIF_PRIORITY = {"pendente": 0, "violacao": 1, "investigar": 2, "nao_violacao": 3}
```

- [ ] **Step 3: Ordenar `filtered_results` antes do loop de exibição**

Logo após a list comprehension `filtered_results = [...]`, adicionar:

```python
filtered_results = sorted(
    filtered_results,
    key=lambda r: (
        _CLASSIF_PRIORITY.get(classifs.get(r.get("page_url", ""), "pendente"), 0),
        _site_priority(r),
    ),
)
```

- [ ] **Step 4: Testar manualmente**

Buscar imagem, verificar que resultados pendentes aparecem antes dos já classificados, e que sites comerciais aparecem antes de redes sociais dentro de cada grupo.

- [ ] **Step 5: Commit**

```bash
git add src/ui/app.py
git commit -m "feat(ui): ordenar resultados por status (pendente primeiro) e tipo de site"
```

---

## Task 4: Loading progressivo com st.status

**Files:**
- Modify: `src/ui/app.py`

Substituir o `st.spinner` genérico por `st.status` expandido que mostra o progresso real de cada API (FaceCheck e Google Vision), dando feedback imediato ao usuário. Requer importar os clients diretamente para mostrar contagens por fonte.

- [ ] **Step 1: Atualizar imports em app.py**

Substituir o import do search orchestrator por imports individuais:

```python
# Antes:
from src.search.orchestrator import search_image

# Depois:
from src.search.aggregator import aggregate
from src.search.facecheck_client import search_by_face
from src.search.google_vision_client import search_by_image
from src.search.orchestrator import search_image  # mantido como fallback
```

- [ ] **Step 2: Substituir o bloco de busca no app.py**

Localizar o bloco que começa em:
```python
if st.button("Buscar ocorrências", type="primary", use_container_width=False):
    with st.spinner("Buscando em FaceCheck e Google Vision..."):
```

Substituir pelo seguinte (mantendo o bloco de `tempfile` e `try/finally` ao redor):

```python
if st.button("Buscar ocorrências", type="primary", use_container_width=False):
    suffix = os.path.splitext(uploaded_file.name)[-1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        import asyncio as _asyncio
        import concurrent.futures
        import time

        # Inicializar com dicts de erro seguro — garante que aggregate() nunca receba None
        _err = {"status": "error", "results": [], "message": "não executado"}
        fc_result = _err
        gv_result = _err

        with st.status("🔍 Buscando ocorrências...", expanded=True) as search_status:
            ph_fc = st.empty()
            ph_gv = st.empty()
            ph_fc.info("⏳ FaceCheck: aguardando...")
            ph_gv.info("⏳ Google Vision: aguardando...")

            def _run_fc():
                # IMPORTANTE: usar asyncio.run() — não _run_async().
                # Worker threads não têm event loop; asyncio.run() cria e destrói um loop
                # por chamada, o que é o padrão correto e seguro para threads.
                try:
                    return _asyncio.run(search_by_face(tmp_path))
                except Exception as exc:
                    return {"status": "error", "results": [], "message": str(exc)}

            def _run_gv():
                try:
                    return _asyncio.run(search_by_image(tmp_path))
                except Exception as exc:
                    return {"status": "error", "results": [], "message": str(exc)}

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                fc_future = executor.submit(_run_fc)
                gv_future = executor.submit(_run_gv)

                fc_shown = False
                gv_shown = False
                while not (fc_future.done() and gv_future.done()):
                    if fc_future.done() and not fc_shown:
                        fc_result = fc_future.result()
                        n = len(fc_result.get("results", []))
                        ph_fc.success(f"✅ FaceCheck: {n} resultado(s)")
                        fc_shown = True
                    if gv_future.done() and not gv_shown:
                        gv_result = gv_future.result()
                        n = len(gv_result.get("results", []))
                        ph_gv.success(f"✅ Google Vision: {n} resultado(s)")
                        gv_shown = True
                    time.sleep(0.15)

                if not fc_shown:
                    fc_result = fc_future.result()
                    n = len(fc_result.get("results", []))
                    ph_fc.success(f"✅ FaceCheck: {n} resultado(s)")
                if not gv_shown:
                    gv_result = gv_future.result()
                    n = len(gv_result.get("results", []))
                    ph_gv.success(f"✅ Google Vision: {n} resultado(s)")

            result = aggregate(fc_result, gv_result)
            total = result.get("total_deduplicated", 0)
            search_status.update(
                label=f"✅ {total} resultado(s) encontrado(s)",
                state="complete",
                expanded=False,
            )

    except Exception as exc:
        st.error(f"Erro na busca de imagem: {exc}")
        result = None
    finally:
        os.unlink(tmp_path)

    if result is not None:
        st.session_state.search_result = result
        st.session_state.classifications = {}
        st.rerun()
```

**Notas de implementação:**
- `st.status` disponível a partir do Streamlit 1.28.0. `requirements.txt` especifica `>=1.32.0` — compatível.
- `asyncio.run()` nos workers é obrigatório. `_run_async()` chama `asyncio.new_event_loop()` e pode gerar conflito de loops em threads; `asyncio.run()` cria e destrói um loop isolado por chamada.
- O `while` loop de polling roda no **thread principal** do Streamlit e bloqueia o script durante toda a busca (igual ao `st.spinner` original). O app ficará sem resposta a outras interações durante esse tempo — comportamento idêntico ao estado atual, mas com feedback visual por API.
- `ph_fc.success(...)` e `ph_gv.success(...)` são chamados do thread principal, nunca dos workers — isso é correto e seguro para o Streamlit.

- [ ] **Step 3: Testar manualmente**

```bash
streamlit run src/ui/app.py
```

Carregar uma imagem e buscar. Verificar que aparecem dois indicadores de progresso ("FaceCheck: aguardando..." e "Google Vision: aguardando..."), e que cada um muda para "✅ X resultado(s)" à medida que a API responde. O status geral fecha com o total ao final.

- [ ] **Step 4: Commit**

```bash
git add src/ui/app.py
git commit -m "feat(ui): loading progressivo com st.status e paralelismo real entre APIs"
```

---

## Verificação final

- [ ] **Rodar suite completa de testes unitários**

```bash
cd poc-orquestrador
python -m pytest tests/ -v --ignore=tests/test_lookup.py -k "not real_domain and not real_image"
```

Esperado: todos PASSED.

- [ ] **Teste de fumaça end-to-end no Streamlit**

```bash
streamlit run src/ui/app.py
```

Checklist manual:
1. ✅ Cards exibem thumbnail ao lado esquerdo
2. ✅ Filtro "Ocultar redes sociais" ativo por default remove Instagram etc.
3. ✅ Resultados pendentes aparecem primeiro; sites antes de redes sociais
4. ✅ Busca mostra progresso individual por API (FaceCheck / Google Vision)
5. ✅ PDF gerado tem logo Goulart|Law no header e rodapé com nome do escritório
6. ✅ PDF contém imagens embutidas das violações
7. ✅ PDF contém campos: Nome Fantasia, Atividade, Telefone, E-mail, CEP, Natureza Jurídica, Capital Social, Fonte API
8. ✅ PDF contém link Google Maps do endereço da empresa

---

## Próxima sprint: Amazon Rekognition (aguarda credencial AWS)

**Escopo:**
- Novo arquivo: `src/search/rekognition_client.py`
- Fluxo: Google Vision retorna `image_url` → Rekognition `compare_faces(original_path, image_url)` → adiciona `confidence` ao resultado do Vision
- Atualização em `src/search/orchestrator.py`: etapa pós-Vision de enriquecimento de scores
- Atualização em `src/search/aggregator.py`: nenhuma — já ordena por `confidence`
- Não afeta FaceCheck (já tem score próprio)

**Credenciais necessárias:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
