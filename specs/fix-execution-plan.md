# POC Orquestrador — Plano de Correções Pós-Validação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os 15 itens identificados no relatório de validação `specs/validation-report.md`, do mais crítico ao mais baixo risco, sem alterar comportamento externo do sistema.

**Architecture:** Correções cirúrgicas por arquivo — sem refatorações globais. Cada task é independente e termina com testes passando e commit. O plano parte dos riscos de corrupção de dados (Alta prioridade) e vai até melhorias de qualidade (Baixa prioridade).

**Tech Stack:** Python 3.10+, Streamlit, pytest, asyncio, httpx, WeasyPrint, unittest.mock

**Working directory:** `poc-orquestrador/` — todos os comandos devem ser rodados a partir desta pasta.

**Rodar testes unitários base antes de começar:**
```bash
cd poc-orquestrador
pytest tests/ -v --ignore=tests/test_search.py -k "not integration"
```
Todos devem passar antes de qualquer alteração.

---

## Mapa de arquivos modificados

| Arquivo | Tasks |
|---------|-------|
| `src/export/dossie_generator.py` | Task 1 |
| `src/export/pdf_exporter.py` | Task 2 |
| `src/ui/app.py` | Task 3, Task 4 |
| `src/lookup/orchestrator.py` | Task 5 |
| `src/lookup/cnpj_client.py` | Task 6 |
| `src/lookup/jucesp_client.py` | Task 7 |
| `tests/conftest.py` | Task 8 |
| `tests/test_lookup.py` | Task 9 |
| `tests/test_export.py` | Task 10 |

---

## Task 1: Corrigir `_render_investigate_item` — substituir .replace() por parâmetro

**Risco atual:** `.replace(f"### Violação {index}", f"### Investigação {index}", 1)` em `dossie_generator.py:122` corrompe silenciosamente o dossiê se qualquer campo de dado (URL, razão social, etc.) contiver a string "Violação N".

**Arquivo:**
- Modificar: `src/export/dossie_generator.py`
- Modificar: `tests/test_export.py`

- [ ] **Step 1: Escrever o teste que detecta o bug atual**

Em `tests/test_export.py`, adicionar dentro de `class TestDossieGenerator`:

```python
def test_investigate_item_header_when_razao_social_contains_violacao(self):
    """_render_investigate_item não deve corromper dados que contêm 'Violação'."""
    item = _make_item(
        razao_social="Empresa Violação 1 Ltda",  # dado contém "Violação 1"
        page_url="https://investigate.com/page",
        domain="investigate.com",
    )
    md = generate(
        client_name="Cliente",
        violations=[],
        investigate=[item],
        date="2026-03-18",
    )
    # O cabeçalho do bloco deve ser "Investigação 1", não "### Violação 1"
    assert "### Investigação 1" in md
    # A razão social não deve ter sido modificada
    assert "Empresa Violação 1 Ltda" in md
```

- [ ] **Step 2: Rodar para confirmar que o teste FALHA**

```bash
pytest tests/test_export.py::TestDossieGenerator::test_investigate_item_header_when_razao_social_contains_violacao -v
```
Esperado: **FAIL** — o `.replace()` atual vai substituir a string errada.

- [ ] **Step 3: Refatorar `_render_item` para aceitar parâmetro `label`**

Em `src/export/dossie_generator.py`, modificar a assinatura e o f-string inicial de `_render_item`:

```python
def _render_item(index: int, item: dict, label: str = "Violação") -> str:
    """Renderiza um item (violação ou investigação) como bloco markdown."""
    search = _as_dict(item.get("search_result") if isinstance(item, dict) else None)
    lookup = _as_dict(item.get("lookup") if isinstance(item, dict) else None)

    whois = _as_dict(lookup.get("whois"))
    cnpj_data = _as_dict(lookup.get("cnpj_data"))
    jucesp = _as_dict(lookup.get("jucesp"))
    summary = _as_dict(lookup.get("summary"))

    page_url = _v(search.get("page_url"))
    domain = _v(search.get("domain"))
    razao_social = _v(summary.get("razao_social"))
    cnpj = _v(cnpj_data.get("cnpj") or summary.get("cnpj"))
    socios = _format_socios(cnpj_data.get("socios", []))
    situacao = _v(cnpj_data.get("situacao"))
    logradouro = _v(cnpj_data.get("logradouro") or summary.get("address"))
    municipio = cnpj_data.get("municipio") or ""
    uf = cnpj_data.get("uf") or ""
    endereco = logradouro
    if municipio and logradouro != _PLACEHOLDER:
        endereco = f"{logradouro}, {municipio}/{uf}" if uf else f"{logradouro}, {municipio}"
    whois_dates = _format_whois_dates(whois)
    registrant = _v(whois.get("registrant"))
    jucesp_url = _v(jucesp.get("jucesp_search_url"))
    confidence = _format_confidence(search)

    thumbnail = search.get("preview_thumbnail") or ""
    image_block = (
        f'\n<img src="{thumbnail}" style="max-width:240px;max-height:240px;'
        f'border:1px solid #ccc;margin:6px 0;display:block;">\n'
        if thumbnail.startswith("data:")
        else ""
    )

    return (
        f"### {label} {index}\n"
        f"{image_block}"
        f"- **URL:** {page_url}\n"
        f"- **Domínio:** {domain}\n"
        f"- **Empresa responsável:** {razao_social}\n"
        f"- **CNPJ:** {cnpj}\n"
        f"- **Responsável:** {socios}\n"
        f"- **Situação:** {situacao}\n"
        f"- **Endereço:** {endereco}\n"
        f"- **WHOIS:** {whois_dates}\n"
        f"- **Registrante WHOIS:** {registrant}\n"
        f"- **JUCESP:** {jucesp_url}\n"
        f"- **Confiança da busca:** {confidence}\n"
    )
```

- [ ] **Step 4: Simplificar `_render_investigate_item`**

Substituir o corpo de `_render_investigate_item`:

```python
def _render_investigate_item(index: int, item: dict) -> str:
    """Mesmo formato mas com cabeçalho 'Investigação'."""
    return _render_item(index, item, label="Investigação")
```

- [ ] **Step 5: Rodar todos os testes do módulo export**

```bash
pytest tests/test_export.py -v
```
Esperado: **todos PASS**, incluindo o novo.

- [ ] **Step 6: Commit**

```bash
git add src/export/dossie_generator.py tests/test_export.py
git commit -m "fix: refactor _render_investigate_item to use label param instead of str.replace"
```

---

## Task 2: Adicionar tratamento de erro em `pdf_exporter.py`

**Risco atual:** Falha do WeasyPrint (dependência de sistema ausente, permissão de escrita negada, etc.) propaga como traceback bruto sem mensagem amigável.

**Arquivo:**
- Modificar: `src/export/pdf_exporter.py`
- Modificar: `tests/test_export.py`

- [ ] **Step 1: Escrever teste que verifica mensagem amigável em falha**

Em `tests/test_export.py`, adicionar dentro de `class TestPdfExporter`:

```python
def test_to_bytes_raises_runtime_error_with_message_on_failure(self):
    """Falha do WeasyPrint deve virar RuntimeError com mensagem amigável."""
    from unittest.mock import patch, MagicMock
    from src.export.pdf_exporter import to_bytes

    with patch("src.export.pdf_exporter.HTML") as mock_html:
        mock_html.return_value.write_pdf.side_effect = Exception("cairo not found")
        with pytest.raises(RuntimeError, match="Erro ao gerar PDF"):
            to_bytes("# Teste")
```

- [ ] **Step 2: Rodar para confirmar FAIL**

```bash
pytest tests/test_export.py::TestPdfExporter::test_to_bytes_raises_runtime_error_with_message_on_failure -v
```
Esperado: **FAIL** — atualmente propaga `Exception` diretamente, não `RuntimeError`.

- [ ] **Step 3: Adicionar tratamento de erro em `to_bytes` e `export`**

Em `src/export/pdf_exporter.py`, modificar as duas funções públicas:

```python
def export(markdown_text: str, output_path: str) -> str:
    """
    Converte markdown em PDF e salva em output_path.

    Args:
        markdown_text: conteúdo markdown do dossiê.
        output_path: caminho do arquivo PDF de saída.

    Returns:
        output_path confirmado.

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

    Args:
        markdown_text: conteúdo markdown do dossiê.

    Returns:
        bytes do PDF gerado.

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

- [ ] **Step 4: Rodar todos os testes de export**

```bash
pytest tests/test_export.py -v
```
Esperado: **todos PASS**.

- [ ] **Step 5: Commit**

```bash
git add src/export/pdf_exporter.py tests/test_export.py
git commit -m "fix: wrap WeasyPrint errors in RuntimeError with user-friendly message"
```

---

## Task 3: Adicionar tratamento de erros na UI (busca + exportação)

**Risco atual:** Falha em `search_image()` ou em `to_bytes()` dentro do Streamlit gera traceback bruto na tela do Ulysses.

**Arquivo:**
- Modificar: `src/ui/app.py`

> Nota: `app.py` não tem testes unitários automatizados (Streamlit). Verificação é manual via execução do app ou inspeção de código.

- [ ] **Step 1: Envolver a busca com try/except**

Localizar o bloco que chama `_run_async(search_image(tmp_path))` (próximo da linha 123) e substituir por:

```python
                try:
                    result = _run_async(search_image(tmp_path))
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

> Atenção: remover o `finally: os.unlink(tmp_path)` existente pois foi incorporado no novo bloco acima.

- [ ] **Step 2: Envolver a geração de PDF com try/except**

Localizar a chamada `pdf_bytes = pdf_to_bytes(markdown_text)` (próximo da linha 316) e substituir por:

```python
                    try:
                        pdf_bytes = pdf_to_bytes(markdown_text)
                    except RuntimeError as exc:
                        st.error(str(exc))
                        pdf_bytes = None
```

E envolver o `st.download_button` em um `if pdf_bytes is not None:`:

```python
                if pdf_bytes is not None:
                    filename = f"dossie_{client_name.lower().replace(' ', '_')}_{today}.pdf"
                    st.download_button(
                        label="Baixar Dossiê PDF",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                        type="primary",
                    )

                    with st.expander("Pré-visualizar markdown do dossiê"):
                        st.markdown(markdown_text)
```

- [ ] **Step 3: Inspecionar que não há `os.unlink` duplicado**

```bash
grep -n "os.unlink" src/ui/app.py
```
Esperado: aparecer **exatamente 1 vez**.

- [ ] **Step 4: Commit**

```bash
git add src/ui/app.py
git commit -m "fix: add try/except for search and PDF export errors in Streamlit UI"
```

---

## Task 4: Corrigir problemas de qualidade na UI

**Itens desta task:**
- `_passes_filter` redefinida a cada rerun (linha ~171)
- Conflito de nome de variável `domain` (linha ~286 e ~198)
- Bug cosmético nos botões: asteriscos Markdown em label (linha ~229)
- `_run_async` usando `get_event_loop()` depreciado no Python 3.10+

**Arquivo:**
- Modificar: `src/ui/app.py`

- [ ] **Step 1: Mover `_passes_filter` para o bloco de helpers**

Remover a definição de `_passes_filter` de dentro do bloco `if "search_result" in st.session_state` e mover para o bloco de helpers (após `_classify`). A função recebe `filter_sources`, `conf_min`, `conf_max` e `include_no_conf` como parâmetros — mas no Streamlit com closures, ela captura as variáveis do scope. Para evitar dependência de closure, transformar em função com parâmetros explícitos:

```python
def _passes_filter(
    item: dict,
    filter_sources: list,
    conf_min: float,
    conf_max: float,
    include_no_conf: bool,
) -> bool:
    if item.get("source") not in filter_sources:
        return False
    conf = item.get("confidence")
    if conf is None:
        return include_no_conf
    return conf_min <= conf <= conf_max
```

E atualizar a chamada no corpo do arquivo:

```python
filtered_results = [
    r for r in results
    if _passes_filter(r, filter_sources, conf_min, conf_max, include_no_conf)
]
```

- [ ] **Step 2: Renomear `domain` no loop de exportação**

Na seção de exportação (próximo da linha 286), renomear a variável de loop de `domain` para `d` para evitar conflito com o `domain` da seção de resultados:

```python
                    for d, lr in zip(unique_domains, lookup_results):
                        if isinstance(lr, Exception):
                            domain_lookup[d] = {}
                        else:
                            domain_lookup[d] = lr
```

- [ ] **Step 3: Corrigir label do botão de violação ativo**

Localizar o botão com label `"✅ *Violação*"` e remover os asteriscos:

```python
                    if st.button(
                        "✅ Violação",
                        key=f"v_{url}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                    ):
```

- [ ] **Step 4: Corrigir `_run_async` para Python 3.10+**

Substituir o corpo de `_run_async`:

```python
def _run_async(coro):
    """Executa coroutine em contexto síncrono (Streamlit não é async)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
```

- [ ] **Step 5: Verificar que o arquivo não tem erros de sintaxe**

```bash
python -c "import ast; ast.parse(open('src/ui/app.py').read()); print('OK')"
```
Esperado: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/ui/app.py
git commit -m "fix: move _passes_filter to helpers, fix domain var conflict, fix button label, update _run_async"
```

---

## Task 5: Corrigir `lookup/orchestrator.py` — re-import e `_no_cnpj_result` async

**Itens desta task:**
- Re-import dinâmico desnecessário de `lookup_jucesp` (linha 108)
- `_no_cnpj_result` declarada `async` sem nenhum `await`

**Arquivo:**
- Modificar: `src/lookup/orchestrator.py`
- Verificar: `tests/test_lookup.py` (não deve precisar de alteração)

- [ ] **Step 1: Remover re-import dinâmico**

Localizar as linhas 107-109:

```python
    if cnpj_result.get("razao_social") and jucesp_result.get("status") == "manual_required":
        from .jucesp_client import lookup_jucesp as _jucesp
        jucesp_result = await _jucesp(cnpj_result["razao_social"], cnpj_result.get("cnpj"))
```

Substituir por (usando o import já existente no topo do arquivo):

```python
    if cnpj_result.get("razao_social") and jucesp_result.get("status") == "manual_required":
        jucesp_result = await lookup_jucesp(cnpj_result["razao_social"], cnpj_result.get("cnpj"))
```

- [ ] **Step 2: Converter `_no_cnpj_result` de `async def` para `def`**

Localizar:

```python
async def _no_cnpj_result(domain: str) -> dict:
```

Substituir por:

```python
def _no_cnpj_result(domain: str) -> dict:
```

> Nota: a função é chamada como `_no_cnpj_result(domain)` (sem await) no corpo de `lookup_domain` — verifique que não há `await` antes da chamada. Caso exista, remover o `await` também.

- [ ] **Step 3: Verificar chamada sem await**

```bash
grep -n "_no_cnpj_result" src/lookup/orchestrator.py
```

Esperado: a linha de chamada deve ser `cnpj_coro = _no_cnpj_result(domain)` **sem** `await` (correto — já é chamada como coroutine dentro do gather, mas como a função não é mais async, precisa ser ajustada).

> Atenção: `_no_cnpj_result` é usada como `cnpj_coro = _no_cnpj_result(domain)` dentro de um `asyncio.gather`. Como `gather` espera coroutines ou futures, e a função agora retorna um dict síncrono, usar `asyncio.coroutine` não funciona mais. A solução é envolver com uma coroutine inline:

```python
    async def _no_cnpj():
        return _no_cnpj_result(domain)
    cnpj_coro = _no_cnpj()
```

Ou usar `asyncio.coroutine` não é mais recomendado. A forma correta no Python moderno:

```python
    cnpj_coro = asyncio.coroutine(lambda: _no_cnpj_result(domain))()
```

O mais limpo é manter `_no_cnpj_result` async mas documentar por que:

```python
async def _no_cnpj_result(domain: str) -> dict:
    """
    Resultado padrão quando nenhum CNPJ é extraído do WHOIS.
    Declarada async para compatibilidade com asyncio.gather em lookup_domain.
    """
    return { ... }
```

**Decisão:** manter `async def` e apenas adicionar o comentário de justificativa. O ponto do relatório era a falta de documentação, não a assinatura em si.

- [ ] **Step 3 (revisado): Adicionar comentário em `_no_cnpj_result`**

```python
async def _no_cnpj_result(domain: str) -> dict:
    """
    Resultado padrão quando nenhum CNPJ é extraído do WHOIS.
    Declarada async para compatibilidade com asyncio.gather em lookup_domain — sem I/O.
    """
    return {
        "cnpj": None,
        ...
    }
```

- [ ] **Step 4: Rodar testes de lookup**

```bash
pytest tests/test_lookup.py -v -k "not integration"
```
Esperado: **todos PASS**.

- [ ] **Step 5: Commit**

```bash
git add src/lookup/orchestrator.py
git commit -m "fix: remove dynamic import in orchestrator, document _no_cnpj_result async rationale"
```

---

## Task 6: Unificar `_not_found_result` e `_error_result` em `cnpj_client.py`

**Risco atual:** Os dois helpers têm schema de 14 campos idêntico exceto por `status` — qualquer mudança de schema precisa ser feita em dois lugares.

**Arquivo:**
- Modificar: `src/lookup/cnpj_client.py`
- Verificar: `tests/test_lookup.py` (não deve precisar de alteração)

- [ ] **Step 1: Criar helper unificado e remover os dois antigos**

Em `src/lookup/cnpj_client.py`, substituir `_not_found_result` e `_error_result` por:

```python
def _build_empty_result(cnpj_raw: str, status: str, message: str) -> dict:
    """Schema base para resultados sem dados (not_found ou error)."""
    return {
        "cnpj": cnpj_raw,
        "razao_social": None,
        "nome_fantasia": None,
        "situacao": None,
        "atividade_principal": None,
        "logradouro": None,
        "socios": [],
        "telefone": None,
        "email": None,
        "cep": None,
        "bairro": None,
        "natureza_juridica": None,
        "capital_social": None,
        "fonte": None,
        "status": status,
        "requires_manual_review": True,
        "message": message,
    }


def _not_found_result(cnpj_raw: str, message: str) -> dict:
    return _build_empty_result(cnpj_raw, "not_found", message)


def _error_result(cnpj_raw: str, message: str) -> dict:
    return _build_empty_result(cnpj_raw, "error", message)
```

> Nota: manter `_not_found_result` e `_error_result` como wrappers finos preserva todos os call sites sem alteração.

- [ ] **Step 2: Rodar testes de lookup**

```bash
pytest tests/test_lookup.py -v -k "not integration"
```
Esperado: **todos PASS** — a interface pública não mudou.

- [ ] **Step 3: Commit**

```bash
git add src/lookup/cnpj_client.py
git commit -m "refactor: unify _not_found_result and _error_result in cnpj_client via shared _build_empty_result"
```

---

## Task 7: Melhorar URL de busca do JUCESP

**Item:** `jucesp_client.py` retorna sempre a URL base sem parâmetros. Uma URL com o nome da empresa pré-preenchido reduziria o trabalho manual do Ulysses.

**Arquivo:**
- Modificar: `src/lookup/jucesp_client.py`
- Modificar: `tests/test_lookup.py`

- [ ] **Step 1: Atualizar teste existente para nova URL com parâmetros**

Em `tests/test_lookup.py`, na classe `TestJucespClient`, o teste `test_builds_url_with_razao_social` atualmente verifica apenas `"jucesponline.sp.gov.br" in result["jucesp_search_url"]`. Atualizar para verificar também a presença de um parâmetro de busca quando razão social é fornecida:

```python
async def test_builds_url_with_razao_social(self):
    """URL gerada aponta para o portal JUCESP Online com razão social como parâmetro."""
    from src.lookup.jucesp_client import lookup_jucesp

    result = await lookup_jucesp("Empresa Exemplo Ltda", "11222333000181")

    assert "jucesponline.sp.gov.br" in result["jucesp_search_url"]
    assert result["status"] == "manual_required"
    # URL deve conter parâmetro de busca quando razão social é fornecida
    assert "Empresa" in result["jucesp_search_url"] or "q=" in result["jucesp_search_url"]
```

- [ ] **Step 2: Rodar para confirmar que FALHA (URL atual não tem parâmetros)**

```bash
pytest tests/test_lookup.py::TestJucespClient::test_builds_url_with_razao_social -v
```
Esperado: **FAIL**.

- [ ] **Step 3: Atualizar `jucesp_client.py` para gerar URL com parâmetro**

```python
from urllib.parse import quote_plus

_JUCESP_BASE_URL = "https://www.jucesponline.sp.gov.br"
_JUCESP_SEARCH_URL = _JUCESP_BASE_URL + "/BuscaEmpresa?nome={nome}"


async def lookup_jucesp(razao_social: str | None, cnpj: str | None) -> dict:
    """
    Retorna link direto para consulta manual na JUCESP Online.

    Sempre retorna requires_manual_review=True — sem exceções.
    Declarada async para compatibilidade com asyncio.gather em lookup_domain.

    Args:
        razao_social: nome da empresa (informativo e usado na URL de busca).
        cnpj: CNPJ da empresa (informativo no retorno).

    Returns:
        dict com jucesp_search_url e status "manual_required".
    """
    if razao_social:
        jucesp_url = _JUCESP_SEARCH_URL.format(nome=quote_plus(razao_social))
        message = "Consulta JUCESP requer verificação manual — link direto gerado para agilizar"
    elif cnpj:
        jucesp_url = _JUCESP_BASE_URL
        message = "Consulta JUCESP requer verificação manual — link direto gerado para agilizar"
    else:
        jucesp_url = _JUCESP_BASE_URL
        message = "Empresa não identificada — acesse JUCESP manualmente para busca"

    return {
        "razao_social": razao_social,
        "cnpj": cnpj,
        "jucesp_search_url": jucesp_url,
        "contrato_social_url": None,  # reservado para fase 2 (scraping com Playwright)
        "status": "manual_required",
        "requires_manual_review": True,
        "message": message,
    }
```

- [ ] **Step 4: Atualizar o teste `test_none_inputs_returns_base_url` para garantir que `None, None` ainda retorna URL base**

Verificar que o teste existente ainda passa (não precisa alterar).

- [ ] **Step 5: Rodar todos os testes de lookup**

```bash
pytest tests/test_lookup.py -v -k "not integration"
```
Esperado: **todos PASS**.

- [ ] **Step 6: Commit**

```bash
git add src/lookup/jucesp_client.py tests/test_lookup.py
git commit -m "feat: generate parametrized JUCESP search URL when razao_social is available"
```

---

## Task 8: Adicionar fixtures compartilhadas no `conftest.py`

**Item:** Builders `_make_*` duplicados entre arquivos de teste. Centralizar os mais reutilizados.

**Arquivo:**
- Modificar: `tests/conftest.py`

> Nota: não mover fixtures que são usadas por apenas um arquivo. Mover apenas o que é compartilhado.

- [ ] **Step 1: Identificar builders duplicados**

```bash
grep -rn "def _make_" tests/
```

Analisar quais aparecem em mais de um arquivo.

- [ ] **Step 2: Adicionar fixture de `sample_search_result` no conftest**

Em `tests/conftest.py`, adicionar:

```python
"""
Configuração global do pytest.

Carrega .env antes de qualquer teste para garantir que variáveis de ambiente
(ex: CNPJ_REQUEST_DELAY_MS) estejam disponíveis nos testes assíncronos.
"""

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    load_dotenv()


@pytest.fixture
def sample_search_item():
    """Item de busca padrão para testes de export e UI."""
    return {
        "image_url": None,
        "page_url": "https://example.com/page",
        "domain": "example.com",
        "source": "facecheck",
        "confidence": 0.87,
        "preview_thumbnail": None,
    }


@pytest.fixture
def sample_lookup_result():
    """Resultado de lookup padrão para testes de export."""
    return {
        "whois": {
            "registrant": "Empresa Exemplo Ltda",
            "created": "2020-01-01",
            "expiration_date": "2026-01-01",
        },
        "cnpj_data": {
            "cnpj": "12.345.678/0001-99",
            "razao_social": "Empresa Exemplo Ltda",
            "situacao": "ATIVA",
            "logradouro": "Rua das Flores, 123",
            "municipio": "São Paulo",
            "uf": "SP",
            "socios": [{"nome": "João da Silva", "qualificacao": "Sócio Administrador"}],
        },
        "jucesp": {
            "jucesp_search_url": "https://www.jucesponline.sp.gov.br/BuscaEmpresa?nome=Empresa+Exemplo+Ltda",
        },
        "summary": {
            "razao_social": "Empresa Exemplo Ltda",
            "cnpj": "12.345.678/0001-99",
            "registrant": "Empresa Exemplo Ltda",
        },
    }
```

- [ ] **Step 3: Rodar toda a suite para garantir que nenhuma fixture conflita**

```bash
pytest tests/ -v -k "not integration"
```
Esperado: **todos PASS** — nenhuma alteração funcional, apenas adição de fixtures opcionais.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared fixtures sample_search_item and sample_lookup_result to conftest"
```

---

## Task 9: Adicionar testes faltantes em `test_lookup.py`

**Itens:** Campo `document` do WHOIS nunca testado com valor não-`None`; `_extract_contacts` com texto WHOIS real nunca exercitado.

**Arquivo:**
- Modificar: `tests/test_lookup.py`

- [ ] **Step 1: Adicionar teste para extração de `document` (owner-id)**

Em `tests/test_lookup.py`, dentro de `class TestWhoisClient`:

```python
async def test_extracts_cnpj_from_owner_id_field(self):
    """WHOIS com campo owner-id contendo CNPJ preenche 'document'."""
    from src.lookup.whois_client import lookup_whois

    fake_parsed = MagicMock()
    fake_parsed.org = "Empresa Exemplo Ltda"
    fake_parsed.emails = "contato@exemplo.com.br"
    fake_parsed.registrar = "Registro.br"
    fake_parsed.creation_date = None
    fake_parsed.expiration_date = None
    fake_parsed.name_servers = ["ns1.exemplo.com.br"]
    # Texto bruto simulando campo owner-id do Registro.br
    fake_parsed.text = (
        "domain: exemplo.com.br\n"
        "ownerid: 11.222.333/0001-81\n"
        "owner: Empresa Exemplo Ltda\n"
    )

    with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
        result = await lookup_whois("exemplo.com.br")

    assert result["status"] == "found"
    assert result["document"] == "11.222.333/0001-81"
```

- [ ] **Step 2: Adicionar teste para `_extract_contacts` com bloco nic-hdl-br**

```python
async def test_extracts_contacts_from_nic_hdl_br_block(self):
    """Bloco nic-hdl-br com person e e-mail é extraído para 'contacts'."""
    from src.lookup.whois_client import lookup_whois

    fake_parsed = MagicMock()
    fake_parsed.org = "Empresa Exemplo Ltda"
    fake_parsed.emails = "contato@exemplo.com.br"
    fake_parsed.registrar = "Registro.br"
    fake_parsed.creation_date = None
    fake_parsed.expiration_date = None
    fake_parsed.name_servers = []
    fake_parsed.text = (
        "nic-hdl-br: ABC123\n"
        "person: João da Silva\n"
        "e-mail: joao@exemplo.com.br\n"
        "country: BR\n"
    )

    with patch("src.lookup.whois_client.whois.whois", return_value=fake_parsed):
        result = await lookup_whois("exemplo.com.br")

    assert result["status"] == "found"
    assert len(result["contacts"]) == 1
    assert result["contacts"][0]["name"] == "João da Silva"
    assert result["contacts"][0]["email"] == "joao@exemplo.com.br"
    assert result["contacts"][0]["id"] == "ABC123"
```

- [ ] **Step 3: Rodar os novos testes**

```bash
pytest tests/test_lookup.py::TestWhoisClient::test_extracts_cnpj_from_owner_id_field tests/test_lookup.py::TestWhoisClient::test_extracts_contacts_from_nic_hdl_br_block -v
```
Esperado: **PASS** (os helpers já existem, só faltava o teste).

- [ ] **Step 4: Rodar todos os testes de lookup**

```bash
pytest tests/test_lookup.py -v -k "not integration"
```
Esperado: **todos PASS**.

- [ ] **Step 5: Commit**

```bash
git add tests/test_lookup.py
git commit -m "test: add coverage for WHOIS document extraction and nic-hdl-br contact parsing"
```

---

## Task 10: Corrigir `test_export.py` — magic bytes e sys.path

**Itens:**
- `sys.path.insert` manual na linha 19 (instalar com `pip install -e .` é a solução correta)
- `test_to_bytes_returns_bytes` não verifica que é PDF válido

**Arquivo:**
- Modificar: `tests/test_export.py`

- [ ] **Step 1: Verificar se há `setup.py` ou `pyproject.toml`**

```bash
ls poc-orquestrador/ | grep -E "setup|pyproject"
```

Se não existir: criar `pyproject.toml` mínimo:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "poc-orquestrador"
version = "0.1.0"
```

Depois instalar em modo editável:

```bash
pip install -e .
```

- [ ] **Step 2: Remover `sys.path.insert` de `test_export.py`**

Remover as linhas:

```python
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

(As outras linhas de `import os` ou `import sys` usadas em outros contextos devem ser preservadas — verificar se há outros usos antes de remover.)

- [ ] **Step 3: Atualizar o teste de PDF para verificar magic bytes**

Localizar `test_to_bytes_returns_bytes` e adicionar:

```python
    def test_to_bytes_returns_bytes(self):
        try:
            import weasyprint  # noqa: F401
        except (ImportError, OSError):
            pytest.skip("WeasyPrint ou dependências do sistema não disponíveis")
        from src.export.pdf_exporter import to_bytes

        md = generate(
            client_name="Teste PDF",
            violations=[_make_item()],
            investigate=[],
            date="2026-03-18",
        )
        result = to_bytes(md)

        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:4] == b"%PDF", "Resultado não é um PDF válido"
```

- [ ] **Step 4: Rodar todos os testes**

```bash
pytest tests/ -v -k "not integration"
```
Esperado: **todos PASS**.

- [ ] **Step 5: Commit final**

```bash
git add tests/test_export.py pyproject.toml
git commit -m "test: verify PDF magic bytes in test_to_bytes, remove sys.path.insert hack"
```

---

## Verificação final

- [ ] **Rodar suite completa**

```bash
pytest tests/ -v -k "not integration" --tb=short
```
Esperado: **todos PASS**, sem warnings relevantes.

- [ ] **Verificar sintaxe de todos os arquivos modificados**

```bash
python -m py_compile src/export/dossie_generator.py src/export/pdf_exporter.py src/ui/app.py src/lookup/orchestrator.py src/lookup/cnpj_client.py src/lookup/jucesp_client.py && echo "Sintaxe OK"
```
Esperado: `Sintaxe OK`

---

*Plano gerado em 2026-03-18 com base em `specs/validation-report.md`.*
