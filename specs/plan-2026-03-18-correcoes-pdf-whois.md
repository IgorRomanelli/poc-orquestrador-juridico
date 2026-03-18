# Correções PDF + WHOIS .com — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir três problemas identificados em produção: thumbnail quebra formatação do dossiê, identidade visual do PDF diverge do modelo do escritório, e domínios .com com privacy proxy não têm o proprietário real identificado.

**Architecture:** Três fixes cirúrgicos e independentes — nenhum altera a interface pública dos módulos. Task 1 corrige um bug de 1 linha em dossie_generator.py. Task 2 melhora CSS e HTML em pdf_exporter.py. Task 3 adiciona um novo cliente RDAP e o integra no orchestrator como fonte complementar ao WHOIS existente.

**Tech Stack:** Python 3.14, WeasyPrint, httpx (já no projeto), markdown-it (via `markdown[extra]`), RDAP (API REST gratuita, sem chave).

---

## Mapa de arquivos

| Arquivo | Ação | Razão |
|---------|------|-------|
| `src/export/dossie_generator.py` | Modificar (1 linha) | Bug: `\n<img>\n` sem linhas em branco quebra parsing da lista markdown |
| `src/export/pdf_exporter.py` | Modificar (CSS + HTML) | Logo pequeno com borda, metadados colapsados na mesma linha |
| `src/lookup/rdap_client.py` | Criar | Novo cliente RDAP para domínios .com/.net/.org |
| `src/lookup/whois_client.py` | Modificar | Detectar privacy proxies conhecidos e sinalizar |
| `src/lookup/orchestrator.py` | Modificar | Integrar RDAP como fallback quando WHOIS retorna proxy |
| `tests/test_export.py` | Modificar | Testes para bug da thumbnail e identidade visual |
| `tests/test_lookup.py` | Criar | Testes para RDAP client e detecção de proxy |

---

## Task 1: Corrigir formatação da lista quando thumbnail está presente

**Files:**
- Modify: `src/export/dossie_generator.py` (linha ~126)
- Modify: `tests/test_export.py`

**Problema:** `image_block` é `\n<img ...>\n` sem linhas em branco ao redor. O parser markdown trata HTML inline dentro de um bloco de texto como parte do parágrafo anterior, colapsando toda a lista `- **campo:**` em texto plano sem formatação.

**Correção:** Adicionar `\n\n` antes e depois do `<img>` — isso cria um bloco HTML standalone, separado da lista markdown que segue.

- [ ] **Step 1: Escrever teste que falha**

Em `tests/test_export.py`, adicionar à classe `TestPdfExporter`:

```python
def test_thumbnail_preserves_list_formatting(self):
    """Imagem embutida não deve quebrar a formatação da lista de campos."""
    from src.export.pdf_exporter import _to_html
    from src.export.dossie_generator import generate

    item = _make_full_item()
    # Simular thumbnail base64 presente
    item["search_result"]["preview_thumbnail"] = "data:image/jpeg;base64,/9j/fake=="

    md = generate(
        client_name="C",
        violations=[item],
        investigate=[],
        date="2026-03-18",
    )
    html = _to_html(md)

    # A lista deve ter sido parseada como <li>, não como texto plano
    assert "<li>" in html, "Campos do dossiê devem ser renderizados como <li>"
    assert "Domínio:" in html
    assert "CNPJ:" in html
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
python3 -m pytest tests/test_export.py::TestPdfExporter::test_thumbnail_preserves_list_formatting -v
```

Esperado: FAIL — o HTML gerado não contém `<li>` quando thumbnail está presente.

- [ ] **Step 3: Aplicar correção em dossie_generator.py**

Localizar em `src/export/dossie_generator.py`:

```python
    image_block = (
        f'\n<img src="{thumbnail}" style="max-width:240px;max-height:240px;'
        f'border:1px solid #ccc;margin:6px 0;display:block;">\n'
        if thumbnail.startswith("data:")
        else ""
    )
```

Substituir por:

```python
    image_block = (
        f'\n\n<img src="{thumbnail}" style="max-width:240px;max-height:240px;'
        f'border:1px solid #ccc;margin:6px 0;display:block;">\n\n'
        if thumbnail.startswith("data:")
        else ""
    )
```

- [ ] **Step 4: Rodar testes**

```bash
python3 -m pytest tests/test_export.py -v
```

Esperado: todos passando (mínimo 22 passed, 1 skipped).

- [ ] **Step 5: Commit**

```bash
git add src/export/dossie_generator.py tests/test_export.py
git commit -m "fix(dossie): separar bloco img com linhas em branco para preservar formatação da lista"
```

---

## Task 2: Melhorar identidade visual do PDF

**Files:**
- Modify: `src/export/pdf_exporter.py`
- Modify: `src/export/dossie_generator.py` (metadados do cabeçalho)
- Modify: `tests/test_export.py`

**Problemas a corrigir:**
1. Logo tem borda indevida (herda do CSS `img { border: 1px solid #ccc }`)
2. Logo pequeno demais (52px) e alinhado à esquerda — referência tem logo centralizado e maior
3. Metadados (Cliente / Data / Gerado por) aparecem na mesma linha — markdown colapsa `\n` único em espaço

### 2a: Remover borda do logo e centralizar

- [ ] **Step 1: Escrever teste que falha**

Em `tests/test_export.py`, adicionar à classe `TestPdfExporterIdentidade`:

```python
def test_doc_header_img_has_no_border(self):
    """Logo no cabeçalho não deve ter borda."""
    from src.export.pdf_exporter import _CSS
    # CSS deve ter regra específica que anula border para .doc-header img
    assert ".doc-header img" in _CSS
    # A regra específica de .doc-header img deve definir border: none
    import re
    match = re.search(r'\.doc-header\s+img\s*\{([^}]+)\}', _CSS)
    assert match, ".doc-header img não tem bloco CSS"
    assert "border: none" in match.group(1) or "border:none" in match.group(1)

def test_doc_header_is_centered(self):
    """Cabeçalho deve ter text-align: center."""
    from src.export.pdf_exporter import _CSS
    import re
    match = re.search(r'\.doc-header\s*\{([^}]+)\}', _CSS)
    assert match
    assert "center" in match.group(1)
```

- [ ] **Step 2: Rodar para confirmar que falham**

```bash
python3 -m pytest tests/test_export.py::TestPdfExporterIdentidade::test_doc_header_img_has_no_border tests/test_export.py::TestPdfExporterIdentidade::test_doc_header_is_centered -v
```

Esperado: FAIL.

- [ ] **Step 3: Atualizar CSS em pdf_exporter.py**

Em `src/export/pdf_exporter.py`, substituir o bloco `.doc-header` e `.doc-header img`:

```css
.doc-header {
    text-align: center;
    margin-bottom: 1.5em;
    padding-bottom: 1em;
    border-bottom: 2px solid #C00000;
}

.doc-header img {
    height: 80px;
    border: none;
    margin: 0 auto;
    display: block;
}
```

- [ ] **Step 4: Rodar testes**

```bash
python3 -m pytest tests/test_export.py -v
```

Esperado: todos passando.

### 2b: Corrigir metadados do cabeçalho (mesma linha → linhas separadas)

**Causa:** em `dossie_generator.py`, `"\n".join(sections)` une os itens com `\n` simples. Markdown colapsa `\n` simples em espaço dentro de um parágrafo. Fix: usar dois espaços de trailing + `\n` (que markdown converte em `<br>`) para manter numa frase compacta mas legível.

- [ ] **Step 5: Escrever teste que falha**

Em `tests/test_export.py`, adicionar à classe `TestPdfExporterIdentidade`:

```python
def test_metadata_renders_on_separate_lines(self):
    """Cliente, Data e Gerado por devem estar em linhas separadas no HTML."""
    from src.export.pdf_exporter import _to_html
    from src.export.dossie_generator import generate

    md = generate(client_name="João Silva", violations=[], investigate=[], date="2026-03-18")
    html = _to_html(md)

    # Cada metadado deve aparecer no HTML — se estão na mesma linha, o <br> deve existir
    assert "João Silva" in html
    assert "2026-03-18" in html
    # Deve haver pelo menos um <br> separando os metadados
    import re
    meta_block = html[html.find("João Silva") - 100 : html.find("João Silva") + 200]
    assert "<br" in meta_block, "Metadados devem ter <br> entre eles"
```

- [ ] **Step 6: Rodar para confirmar que falha**

```bash
python3 -m pytest tests/test_export.py::TestPdfExporterIdentidade::test_metadata_renders_on_separate_lines -v
```

Esperado: FAIL — não há `<br>`.

- [ ] **Step 7: Corrigir em dossie_generator.py**

Em `src/export/dossie_generator.py`, localizar na função `generate()`:

```python
    sections = [
        "# Dossiê de Violação de Imagem",
        f"**Cliente:** {client_name}",
        f"**Data:** {date}",
        "**Gerado por:** Sistema de Busca de Imagem",
        "",
        "---",
```

Substituir por:

```python
    sections = [
        "# Dossiê de Violação de Imagem",
        "",
        f"**Cliente:** {client_name}  \n**Data:** {date}  \n**Gerado por:** Sistema de Busca de Imagem",
        "",
        "---",
```

> **Nota:** dois espaços antes de `\n` = `<br>` em markdown. Os três campos ficam numa mesma frase, separados por quebras de linha dentro do parágrafo — compacto e legível.

- [ ] **Step 8: Rodar testes completos**

```bash
python3 -m pytest tests/test_export.py -v
```

Esperado: todos passando.

- [ ] **Step 9: Commit**

```bash
git add src/export/pdf_exporter.py src/export/dossie_generator.py tests/test_export.py
git commit -m "feat(pdf): centralizar logo, remover borda indevida e corrigir metadados do cabeçalho"
```

---

## Task 3: RDAP + detecção de privacy proxy para domínios .com

**Files:**
- Create: `src/lookup/rdap_client.py`
- Modify: `src/lookup/whois_client.py`
- Modify: `src/lookup/orchestrator.py`
- Create: `tests/test_lookup_rdap.py`

**Contexto:**
- WHOIS para `.com` já funciona (datas são recuperadas). O problema é **privacy proxy** — serviços como "Domains By Proxy, LLC" (GoDaddy), "WhoisGuard" (Namecheap), "PrivacyProtect.org" ocultam o dono real.
- **RDAP** (`https://rdap.org/domain/{domain}`) é o padrão moderno para dados de registro, gratuito, sem API key, retorna JSON estruturado. Para domínios com privacidade, retorna os mesmos dados mascarados — mas com estrutura mais confiável.
- **Estratégia:** (1) detectar proxies conhecidos e sinalizar claramente no dossiê; (2) tentar RDAP para domínios não-.br, usando os dados estruturados disponíveis mesmo quando o dono real está oculto.

### 3a: Criar rdap_client.py

- [ ] **Step 1: Escrever testes**

Criar `tests/test_lookup_rdap.py`:

```python
"""
Testes unitários — rdap_client.
Usa mock do httpx para não fazer chamadas reais de rede.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── fixtures ──────────────────────────────────────────────────────────────────

def _make_rdap_response(domain="example.com", registrant_name="Example Corp",
                         created="2020-01-15T00:00:00Z", expiration="2026-01-15T00:00:00Z",
                         registrar="GoDaddy", status_code=200):
    """Resposta RDAP mínima válida."""
    return {
        "ldhName": domain,
        "events": [
            {"eventAction": "registration", "eventDate": created},
            {"eventAction": "expiration", "eventDate": expiration},
        ],
        "entities": [
            {
                "roles": ["registrar"],
                "vcardArray": ["vcard", [
                    ["fn", {}, "text", registrar],
                ]],
            },
            {
                "roles": ["registrant"],
                "vcardArray": ["vcard", [
                    ["fn", {}, "text", registrant_name],
                ]],
            },
        ],
        "status": ["active"],
    }


class TestRdapClient:

    @pytest.mark.asyncio
    async def test_returns_found_for_valid_domain(self):
        from src.lookup.rdap_client import lookup_rdap

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_rdap_response()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await lookup_rdap("example.com")

        assert result["status"] == "found"
        assert result["registrant"] == "Example Corp"
        assert result["registrar"] == "GoDaddy"
        assert result["creation_date"] == "2020-01-15"
        assert result["expiration_date"] == "2026-01-15"

    @pytest.mark.asyncio
    async def test_returns_not_found_on_404(self):
        from src.lookup.rdap_client import lookup_rdap

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await lookup_rdap("notexist.com")

        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_returns_error_on_timeout(self):
        import httpx
        from src.lookup.rdap_client import lookup_rdap

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client

            result = await lookup_rdap("slow.com")

        assert result["status"] == "error"
        assert result["requires_manual_review"] is True


class TestPrivacyProxyDetection:

    def test_detects_godaddy_proxy(self):
        from src.lookup.whois_client import _is_privacy_proxy
        assert _is_privacy_proxy("Domains By Proxy, LLC") is True

    def test_detects_whoisguard(self):
        from src.lookup.whois_client import _is_privacy_proxy
        assert _is_privacy_proxy("WhoisGuard, Inc.") is True

    def test_detects_privacyprotect(self):
        from src.lookup.whois_client import _is_privacy_proxy
        assert _is_privacy_proxy("PrivacyProtect.org") is True

    def test_real_company_is_not_proxy(self):
        from src.lookup.whois_client import _is_privacy_proxy
        assert _is_privacy_proxy("Globo Comunicações e Participações S.A.") is False

    def test_none_is_not_proxy(self):
        from src.lookup.whois_client import _is_privacy_proxy
        assert _is_privacy_proxy(None) is False
```

- [ ] **Step 2: Rodar para confirmar que falham**

```bash
python3 -m pytest tests/test_lookup_rdap.py -v
```

Esperado: erros de importação (módulos ainda não existem).

- [ ] **Step 3: Criar src/lookup/rdap_client.py**

```python
"""
Cliente RDAP — Registration Data Access Protocol.

Consulta estruturada de dados de domínio via API REST gratuita (sem API key).
Endpoint universal: https://rdap.org/domain/{domain}

Usado como complemento ao WHOIS para domínios .com/.net/.org quando o WHOIS
retorna proxy de privacidade ou dados incompletos.

Status possíveis: "found" | "not_found" | "error"
"""

import httpx

_RDAP_URL = "https://rdap.org/domain/{domain}"
_TIMEOUT = 10.0


# ─── helpers privados ──────────────────────────────────────────────────────────

def _extract_vcard_field(entity: dict, field: str) -> str | None:
    """Extrai campo de um vCard RDAP (ex: 'fn', 'email', 'adr')."""
    vcard = entity.get("vcardArray")
    if not vcard or len(vcard) < 2:
        return None
    for entry in vcard[1]:
        if isinstance(entry, list) and len(entry) >= 4 and entry[0] == field:
            return str(entry[3]).strip() if entry[3] else None
    return None


def _extract_registrant(data: dict) -> str | None:
    """Extrai nome do registrante das entidades RDAP."""
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        if "registrant" in roles:
            return _extract_vcard_field(entity, "fn")
    return None


def _extract_registrar(data: dict) -> str | None:
    """Extrai nome do registrar das entidades RDAP."""
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        if "registrar" in roles:
            return _extract_vcard_field(entity, "fn")
    return None


def _extract_date(data: dict, event_action: str) -> str | None:
    """Extrai data de um evento RDAP (registration, expiration, last changed)."""
    for event in data.get("events", []):
        if event.get("eventAction") == event_action:
            raw = event.get("eventDate", "")
            return raw[:10] if raw else None  # ISO 8601 → só a data
    return None


def _not_found_result(domain: str, message: str) -> dict:
    return {
        "domain": domain,
        "registrant": None,
        "registrar": None,
        "creation_date": None,
        "expiration_date": None,
        "status": "not_found",
        "requires_manual_review": True,
        "message": message,
    }


def _error_result(domain: str, message: str) -> dict:
    return {
        "domain": domain,
        "registrant": None,
        "registrar": None,
        "creation_date": None,
        "expiration_date": None,
        "status": "error",
        "requires_manual_review": True,
        "message": message,
    }


# ─── função pública ────────────────────────────────────────────────────────────

async def lookup_rdap(domain: str) -> dict:
    """
    Consulta RDAP de um domínio.

    Args:
        domain: domínio a consultar (ex: "exemplo.com")

    Returns:
        dict com status explícito e dados estruturados.
    """
    url = _RDAP_URL.format(domain=domain)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/rdap+json"})
    except httpx.TimeoutException:
        return _error_result(domain, "RDAP timeout após 10s")
    except Exception as exc:
        return _error_result(domain, f"RDAP erro: {exc}")

    if resp.status_code == 404:
        return _not_found_result(domain, "RDAP: domínio não encontrado")
    if resp.status_code != 200:
        return _error_result(domain, f"RDAP HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        return _error_result(domain, "RDAP: resposta inválida (não é JSON)")

    registrant = _extract_registrant(data)
    registrar = _extract_registrar(data)
    creation_date = _extract_date(data, "registration")
    expiration_date = _extract_date(data, "expiration")

    if not registrant and not registrar and not creation_date:
        return _not_found_result(domain, "RDAP: sem dados de registrante")

    return {
        "domain": domain,
        "registrant": registrant,
        "registrar": registrar,
        "creation_date": creation_date,
        "expiration_date": expiration_date,
        "status": "found",
        "requires_manual_review": False,
        "message": None,
    }
```

- [ ] **Step 4: Adicionar `_is_privacy_proxy` ao whois_client.py**

Após os imports em `src/lookup/whois_client.py`, adicionar:

```python
_PRIVACY_PROXIES = frozenset({
    "domains by proxy",
    "whoisguard",
    "privacyprotect",
    "perfect privacy",
    "withheld for privacy",
    "privacy protect",
    "contact privacy",
    "redacted for privacy",
    "registrant state/province",
    "data protected",
    "privateregistration",
    "identity protect",
})


def _is_privacy_proxy(registrant: str | None) -> bool:
    """Retorna True se o registrante é um serviço conhecido de privacidade WHOIS."""
    if not registrant:
        return False
    lower = registrant.lower()
    return any(proxy in lower for proxy in _PRIVACY_PROXIES)
```

- [ ] **Step 5: Integrar RDAP no orchestrator**

Em `src/lookup/orchestrator.py`, adicionar import:

```python
from .rdap_client import lookup_rdap
```

E adicionar helper para detectar se deve usar RDAP (domínios não-.br):

```python
def _is_br_domain(domain: str) -> bool:
    return domain.endswith(".br")
```

No corpo de `lookup_domain()`, após o resultado do WHOIS, adicionar RDAP como fallback para domínios não-.br com proxy:

```python
    # Para domínios não-.br: tentar RDAP se WHOIS retornou proxy ou sem dados
    rdap_result = None
    if not _is_br_domain(domain):
        from .whois_client import _is_privacy_proxy
        whois_registrant = whois_result.get("registrant")
        whois_found = whois_result.get("status") == "found"
        if not whois_found or _is_privacy_proxy(whois_registrant):
            rdap_result = await lookup_rdap(domain)
```

E enriquecer o `whois_result` com dados do RDAP quando disponível:

```python
    # Enriquecer WHOIS com RDAP se disponível e com dados melhores
    if rdap_result and rdap_result.get("status") == "found":
        if not whois_result.get("registrant") or _is_privacy_proxy(whois_result.get("registrant")):
            whois_result = dict(whois_result)
            whois_result["registrant"] = rdap_result.get("registrant") or whois_result.get("registrant")
            whois_result["registrar"] = rdap_result.get("registrar")
            whois_result["rdap_source"] = True
        if not whois_result.get("creation_date"):
            whois_result["creation_date"] = rdap_result.get("creation_date")
        if not whois_result.get("expiration_date"):
            whois_result["expiration_date"] = rdap_result.get("expiration_date")
```

E adicionar no retorno final `"rdap": rdap_result` se quiser logar:

```python
    return {
        "domain": domain,
        "status": global_status,
        "requires_manual_review": requires_manual,
        "whois": whois_result,
        "cnpj_data": cnpj_result,
        "jucesp": jucesp_result,
        "summary": _build_summary(whois_result, cnpj_result, jucesp_result),
    }
```

> **Nota:** não adicionar "rdap" ao retorno público para não quebrar o contrato com o dossie_generator. O RDAP enriquece o `whois_result` em memória antes de retornar.

- [ ] **Step 6: Rodar testes**

```bash
python3 -m pytest tests/test_lookup_rdap.py tests/test_export.py -v
```

Esperado: todos passando.

- [ ] **Step 7: Commit**

```bash
git add src/lookup/rdap_client.py src/lookup/whois_client.py src/lookup/orchestrator.py tests/test_lookup_rdap.py
git commit -m "feat(lookup): cliente RDAP para domínios .com e detecção de privacy proxy WHOIS"
```

---

## Ordem de execução recomendada

```
Task 1 (bug thumbnail) → Task 2 (identidade visual) → Task 3 (RDAP)
```

Tasks 1 e 2 são independentes e podem ser executadas em qualquer ordem. Task 3 é independente das outras.

## Notas sobre limitações conhecidas

- **Privacy proxy:** RDAP e WHOIS retornam os mesmos dados mascarados quando o domínio usa privacidade. Não existe API pública que revele o dono real sem custo. Para casos críticos, o Ulysses pode usar uma ferramenta paga (WhoisXMLAPI, SecurityTrails) — fora do escopo desta POC.
- **Domínios .br:** não precisam de RDAP — o Registro.br já fornece dados completos via WHOIS, incluindo CNPJ via campo `owner-id`.
- **Demo mode FaceCheck:** thumbnails são retornadas como base64 apenas em modo produção (FACECHECK_DEMO=false). Em demo, `preview_thumbnail` pode ser `None`.
