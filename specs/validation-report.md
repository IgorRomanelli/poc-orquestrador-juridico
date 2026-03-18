# Relatório de Validação — POC Orquestrador de APIs Jurídicas

**Data:** 2026-03-18
**Escopo:** `poc-orquestrador/src/` + `tests/`
**Método:** Revisão estática por sub-agente dedicado por módulo

---

## Sumário Executivo

| Módulo | Pontuação | Status |
|--------|-----------|--------|
| `src/lookup/` | 8.5/10 | ✅ Bom |
| `src/search/` | 9/10 | ✅ Excelente |
| `src/export/` | 8/10 | ✅ Bom |
| `src/ui/` | 7.5/10 | ✅ Bom |
| `tests/` | 8.5/10 | ✅ Bom |

**Veredicto geral:** A codebase está bem estruturada para uma POC. Há separação clara de responsabilidades, tratamento de erros explícito em todas as camadas e boa cobertura de testes unitários. Os pontos de atenção são cirúrgicos — nenhum deles compromete a funcionalidade atual.

---

## Módulo: `src/lookup/`

### Visão geral
Responsável por consultar, de forma orquestrada, WHOIS + CNPJ (BrasilAPI com fallback para receitaws) + JUCESP para um dado domínio. O orquestrador executa WHOIS sequencialmente (resultado alimenta o CNPJ) e depois dispara CNPJ + JUCESP em paralelo.

---

### `orchestrator.py`

**Avaliação:** Bom

**Estrutura:** Clara e bem documentada. A divisão entre helpers privados e função pública está correta. O fluxo de dois passos (WHOIS sequencial → CNPJ+JUCESP paralelo) está legível no docstring e no código.

**Performance:** `asyncio.gather(return_exceptions=True)` é a abordagem correta. O isolamento de exceções sem cancelar o resultado global é especialmente sólido.

**Tratamento de erros:** Robusto. Cada exceção inesperada é convertida em `_exception_to_error` com `requires_manual_review=True`.

**Sugestões:**

- **Re-import dinâmico na linha 108** — `from .jucesp_client import lookup_jucesp as _jucesp` dentro da função cria risco de confusão e não é necessário; o `lookup_jucesp` já está importado no topo. Substituir pelo import existente.

- **`_no_cnpj_result` é `async` sem nenhum `await`** (linha 128) — a função pode ser síncrona. Não causa erro funcional mas é semanticamente incorreto e pode enganar o leitor.

- **Segunda chamada ao JUCESP** (linhas 107-109) é sequencial após o gather, adicionando latência no caminho feliz. Como JUCESP sempre retorna `manual_required`, a segunda chamada apenas substitui o resultado com praticamente os mesmos dados. Avaliar se é necessária.

---

### `cnpj_client.py`

**Avaliação:** Bom

**Estrutura:** Excelente. Dual-source com fallback explícito e documentado. Os helpers `_not_found_result` e `_error_result` tornam os caminhos de erro consistentes.

**Performance:** O delay configurável (`CNPJ_REQUEST_DELAY_MS`) é aplicado apenas antes da chamada principal — não antes do fallback para receitaws. Esse comportamento é aceitável mas deveria estar documentado explicitamente.

**Tratamento de erros:** Cobre timeout, HTTP 404, 429 e erros genéricos em ambas as fontes.

**Sugestões:**

- **Validação do CNPJ é apenas por tamanho** (14 dígitos) — não verifica os dígitos verificadores do algoritmo da Receita Federal. Para uma POC isso é aceitável, mas pode gerar chamadas HTTP para CNPJs matematicamente inválidos.

- **`_not_found_result` e `_error_result` têm schema idêntico** exceto pelo `status` — considerar uma única função `_build_result(status, cnpj_raw, message)` para eliminar a repetição de ~20 linhas de dict literal.

---

### `whois_client.py`

**Avaliação:** Bom

**Estrutura:** Correto uso de `asyncio.to_thread` + `wait_for` para envolver a biblioteca síncrona `whois`. Os helpers de extração (`_extract_field`, `_extract_contacts`, `_extract_document`) são focados e testáveis.

**Performance:** Timeout de 10s explícito — adequado para WHOIS.

**Tratamento de erros:** Cobre None, timeout e exceção genérica. O fallback `not_found` quando os três campos principais estão ausentes é uma boa heurística.

**Sugestões:**

- **`_CONTACT_BLOCK_RE` com `re.DOTALL`** pode capturar blocos maiores do que o esperado se o texto WHOIS tiver formato irregular. Um regex mais restritivo com âncora de linha seria mais seguro.

- **`registrant_email` pode ser sobrescrito** em dois momentos distintos (linhas 151 e 154-156). A lógica duplicada pode ser simplificada — extrair emails via `_extract_field` e depois normalizar lista → string em um único passo.

---

### `jucesp_client.py`

**Avaliação:** Excelente (dado o escopo declarado)

**Estrutura:** Decisão de design explicitamente documentada no docstring. Para Fase 1 da POC, gerar um link de busca com `manual_required` é a abordagem correta e honesta.

**Performance:** N/A — nenhuma chamada de rede.

**Tratamento de erros:** N/A — sem I/O.

**Sugestões:**

- **`async def` sem `await`** — a função pode ser síncrona. Mantê-la async só faz sentido para compatibilidade de interface com o `asyncio.gather` no orchestrator, o que é uma justificativa válida. Apenas documentar essa escolha.

- **URL de busca não tem parâmetros** — o portal JUCESP Online aceita `?q=` ou busca por nome. Gerar uma URL com o nome da empresa pré-preenchido agilizaria o trabalho manual do Ulysses sem adicionar complexidade técnica.

### Resumo do módulo
**Pontuação geral:** 8.5/10
**Principais forças:** Fluxo paralelo bem estruturado, tratamento de erros explícito e sem silenciamento, fallback documentado no CNPJ.
**Principais oportunidades de melhoria:** Re-import dinâmico desnecessário, `_no_cnpj_result` async sem motivo, repetição de schema nos helpers de erro do CNPJ.

---

## Módulo: `src/search/`

### Visão geral
Responsável por busca de imagem em duas APIs em paralelo (FaceCheck para busca facial, Google Vision para busca reversa), normalização dos resultados para um schema comum e agregação com deduplicação por `page_url`.

---

### `orchestrator.py`

**Avaliação:** Excelente

**Estrutura:** O módulo mais enxuto do projeto — 62 linhas incluindo docstring. Responsabilidade única e bem definida.

**Performance:** `asyncio.gather(return_exceptions=True)` executa as duas APIs em paralelo. `search_time_seconds` via `time.monotonic()` é a métrica correta (não afetada por NTP).

**Tratamento de erros:** Sólido — exceções inesperadas são convertidas sem cancelar o resultado da outra fonte.

**Sugestões:** Nenhuma — o código está adequado para o escopo.

---

### `facecheck_client.py`

**Avaliação:** Bom

**Estrutura:** Boa separação entre `_upload` e `_poll`. O polling com deadline baseado em `time.monotonic()` é mais correto do que contar iterações.

**Performance:** `open()` síncrono dentro de `_upload` (async). Para imagens grandes em produção, usar `asyncio.to_thread`. Para a POC com imagens de clientes (tipicamente < 5MB), é aceitável.

**Tratamento de erros:** Cobre timeout no upload, timeout no polling, erro de API, arquivo não encontrado e token ausente. Cobertura completa.

**Sugestões:**

- **Sem retry no upload** — uma falha transiente de rede aborta toda a busca. Para produção, um retry com backoff exponencial seria recomendado.

- **`_API_TOKEN` é verificado apenas em `search_by_face`** — se `_upload` fosse chamado diretamente (em testes), o check seria ignorado. Mover a validação para `_upload` ou manter como está e garantir que só `search_by_face` seja pública (o que já é o caso).

---

### `google_vision_client.py`

**Avaliação:** Bom

**Estrutura:** Clean. Uso correto de REST direto sem SDK pesado, o que reduz dependências.

**Performance:** Leitura síncrona da imagem + encode base64 antes do await. Para POC, aceitável. A imagem inteira é carregada em memória — adequado para o tamanho esperado.

**Tratamento de erros:** Cobertura explícita de 400, 403, 429 e outros HTTP codes. Tratamento do campo `error` dentro da resposta 200 (API error envelope) está correto.

**Sugestões:**

- **API key na query string da URL** (`?key=...`) aparece em logs HTTP e em traces. Para produção, usar autenticação via service account com bearer token. Para a POC, aceitável.

- **`_not_found_result` tem `requires_manual_review=False`** enquanto `facecheck_client._not_found_result` tem `True`. A assimetria é intencional (Vision sem resultado é mais conclusivo que FaceCheck sem resultado) mas deveria estar documentada.

---

### `aggregator.py`

**Avaliação:** Excelente

**Estrutura:** Módulo puramente funcional — sem I/O, sem estado. Fácil de testar e de raciocinar.

**Performance:** Operações O(n) com sets para deduplicação — eficiente.

**Tratamento de erros:** N/A — sem I/O. Trata adequadamente dicts com keys ausentes via `.get()`.

**Sugestões:**

- **Deduplicação apenas por `page_url` exato** — dois links para a mesma imagem em URLs ligeiramente diferentes (ex: com/sem trailing slash, parâmetros de query) não serão deduplicados. Para a POC com volume baixo, aceitável. Para escala maior, considerar normalização de URL antes da deduplicação.

- **`_extract_domain` duplicado** — a função `_extract_domain` existe em três módulos (`facecheck_client`, `google_vision_client`, `aggregator`). Candidata a ser movida para um `src/utils.py` compartilhado, mas apenas se houver mais candidatos a compartilhamento (não criar utilidade por uma função só).

### Resumo do módulo
**Pontuação geral:** 9/10
**Principais forças:** Orquestrador mínimo e correto, clientes com schema normalizado consistente, aggregator puramente funcional.
**Principais oportunidades de melhoria:** Leitura síncrona de imagem no Vision client, deduplicação de URL poderia ser mais robusta, `_extract_domain` triplicado.

---

## Módulo: `src/export/`

### Visão geral
Responsável por converter os dados curados pelo advogado em markdown estruturado e depois em PDF via WeasyPrint. Opera de forma síncrona (geração de dossiê não é I/O-bound).

---

### `dossie_generator.py`

**Avaliação:** Bom

**Estrutura:** Clara. Helpers privados bem nomeados. O placeholder `_PLACEHOLDER` centralizado é uma boa decisão — garante consistência na UI e no PDF. A função pública `generate()` tem assinatura clara com todos os parâmetros documentados.

**Performance:** N/A — geração de string em memória, sem I/O.

**Tratamento de erros:** Robusto para dados ausentes — nenhum campo causa `KeyError` ou `AttributeError` graças ao `_as_dict()` + `_v()` + `.get()`.

**Sugestões:**

- **`_render_investigate_item` usa `.replace()`** para trocar "Violação" por "Investigação" no output de `_render_item` (linha 122). Se o nome da empresa ou URL contiver a palavra "Violação", o replace incorreto pode corromper o documento. Refatorar para que o cabeçalho seja um parâmetro de `_render_item`.

- **Imagens base64 inline no markdown** (thumbnail) — o bloco HTML embutido no markdown pode não ser renderizado corretamente por todos os conversores PDF. WeasyPrint suporta, mas a dependência de comportamento específico do renderer deve ser documentada.

- **`_render_item` retorna string com `\n` final implícito** via f-string — ao ser adicionado à lista `sections` e depois `"\n".join(sections)`, pode gerar linhas em branco inconsistentes. Impacto visual mínimo mas vale padronizar.

---

### `pdf_exporter.py`

**Avaliação:** Bom

**Estrutura:** Enxuta e correta. Dois pontos de entrada (`export` para arquivo e `to_bytes` para Streamlit). CSS embutido garante portabilidade sem dependência de arquivos externos.

**Performance:** WeasyPrint é síncrono e pode bloquear o event loop se chamado de contexto async. No caso atual (Streamlit com `st.spinner`), o bloqueio é no thread principal do Streamlit — aceitável para a POC de usuário único.

**Tratamento de erros:** Sem tratamento de exceções em `export()` e `to_bytes()`. Uma falha do WeasyPrint (ex: dependência de sistema ausente) vai propagar como exceção não tratada para o Streamlit, resultando em tela de erro.

**Sugestões:**

- **Sem tratamento de erro em `export()` e `to_bytes()`** — se o WeasyPrint falhar (por dependência do sistema ausente, imagem corrompida no markdown, etc.), a exceção propaga para o Streamlit sem mensagem amigável. Adicionar try/except com mensagem de erro clara.

- **Import de `weasyprint` dentro da função** — boa decisão para evitar `ImportError` no load do módulo em ambientes sem WeasyPrint (ex: CI sem dependências de sistema). Manter essa abordagem.

### Resumo do módulo
**Pontuação geral:** 8/10
**Principais forças:** Schema de geração robusto para dados ausentes, CSS autossuficiente, dois pontos de entrada claros.
**Principais oportunidades de melhoria:** Fragil uso de `.replace()` em `_render_investigate_item`, ausência de tratamento de erro no PDF exporter.

---

## Módulo: `src/ui/`

### Visão geral
Interface Streamlit que orquestra o fluxo do usuário: upload → busca → curadoria → exportação de PDF. Único ponto de entrada da aplicação para o Ulysses.

---

### `app.py`

**Avaliação:** Bom

**Estrutura:** Bem organizada em seções comentadas (`sidebar`, `área principal`, `resultados`, `filtros`, `exportação`). Os helpers auxiliares (`_run_async`, `_confidence_label`, `_source_label`, `_init_classifications`, `_classify`) estão corretamente extraídos do fluxo principal.

**Performance e gerenciamento de estado:**

- `_run_async` reutiliza o event loop existente via `get_event_loop()` — funciona na maioria dos casos mas pode falhar em algumas versões do Streamlit que rodam em threads com loops diferentes. A abordagem com `asyncio.new_event_loop()` como fallback mitiga o risco.
- `st.rerun()` a cada clique de classificação causa re-render completo da página. Com muitos resultados (>50), pode ser perceptivelmente lento. Para a POC com volume baixo, aceitável.
- A função `_lookup_all` é definida dentro do handler do botão — funciona mas é não-idiomático. Pode ser uma função de módulo.

**Tratamento de erros e UX:**

- Falha de `search_image()` não tem tratamento de exceção explícito (além do que está dentro do orchestrator). Se o `_run_async` falhar por razão externa, a exceção propaga para o Streamlit sem mensagem amigável.
- O arquivo temporário é criado com `delete=False` e removido manualmente no `finally` — correto. Se o `finally` não executar (processo morto), o arquivo fica em `/tmp`. Aceitável para POC.

**Sugestões:**

- **Sem try/except ao redor de `_run_async(search_image(tmp_path))`** (linha 123) — envolver com try/except para exibir `st.error("Falha na busca...")` ao invés de um traceback no Streamlit.

- **`_passes_filter` definida dentro do bloco de renderização** (linha 171) — é redefinida a cada rerun do Streamlit. Mover para fora do bloco `if "search_result" in st.session_state`.

- **`domain` na linha 286 é redefinida** — o loop `for item in filtered_results` usa `domain` como variável (linha 198) e o `for domain, lr in zip(...)` na exportação (linha 286) usa o mesmo nome, potencialmente causando confusão. Renomear um dos dois para `lookup_domain_name` ou similar.

- **`client_name` sem sanitização** — é inserido diretamente no markdown e no nome do arquivo PDF. Caracteres especiais podem quebrar o nome do arquivo ou o markdown. Para POC de usuário único (Ulysses) o risco é mínimo.

### Resumo do módulo
**Pontuação geral:** 7.5/10
**Principais forças:** Fluxo de usuário claro e bem segmentado, helpers bem nomeados, gerenciamento de estado correto com `session_state`, cleanup de arquivo temporário via `finally`.
**Principais oportunidades de melhoria:** Ausência de try/except no ponto de entrada da busca, `_passes_filter` redefinida a cada rerun, conflito de nome de variável `domain`.

---

## Módulo: `tests/`

### Visão geral
Suite de testes dividida em duas camadas por arquivo: testes unitários com mocks (sempre rodam) e testes de integração com dados reais (skipados por padrão, requerem casos encerrados do Ulysses).

---

### `conftest.py`

**Avaliação:** Adequado

**Fixtures disponíveis:** Apenas `pytest_configure` que carrega `.env`. Simples e correto.

**Sugestões:** Adicionar fixtures compartilhadas (ex: `sample_search_result`, `sample_lookup_result`) que hoje estão duplicadas como funções `_make_*` em cada arquivo de teste.

---

### `test_lookup.py`

**Avaliação:** Excelente

**Cenários cobertos:**
- `whois_client`: found, empty, None response, timeout, exception genérica
- `cnpj_client`: found (BrasilAPI), CNPJ inválido, 404, 429+fallback, brasilapi_error→receitaws, campo `fonte` em todos os paths, `extract_cnpj_from_text` (válido, sem CNPJ, vazio/None)
- `jucesp_client`: URL gerada, `requires_manual_review` sempre True, inputs None, schema de chaves
- `orchestrator`: combinação completa, status partial, isolamento de exceção, prioridade razao_social

**Cenários faltantes:**
- `_extract_contacts` com texto WHOIS real contendo blocos `nic-hdl-br` — testa o regex mais complexo do módulo
- `_extract_document` extraindo CNPJ do campo `owner-id:` no texto bruto
- `name_servers` sendo string (não lista) — o código normaliza, mas não há teste

---

### `test_search.py`

**Avaliação:** Bom

**Cenários cobertos:**
- `facecheck_client`: found, upload error, polling timeout, normalização score→confidence, token ausente
- `google_vision_client`: found, HTTP 403, webDetection vazio, domain sem www, chave ausente
- `aggregator`: deduplicação por page_url, mesmo domínio URLs diferentes, ordenação por confidence, domains únicos, status partial/not_found
- `search orchestrator`: combinação, isolamento FaceCheck error, isolamento Vision error, isolamento exception

**Cenários faltantes:**
- Polling com múltiplas respostas intermediárias antes da final (testa o loop do polling)
- `visuallySimilarImages` sem `pagesWithMatchingImages` (Vision)

---

### `test_export.py`

**Avaliação:** Bom

**Cenários cobertos:**
- `generate()`: seções obrigatórias, placeholder para campos ausentes, separação violação/investigação, listas vazias
- `pdf_exporter`: `to_bytes` retorna bytes, conteúdo refletido no HTML

**Cenários faltantes:**
- `_render_investigate_item` — não testado diretamente; se a palavra "Violação" aparecer nos dados, o replace pode falhar silenciosamente
- Thumbnail base64 — não testado se o bloco HTML é gerado corretamente quando presente

### Resumo da suite de testes
**Pontuação geral:** 8.5/10
**Estimativa de cobertura de branches:** ~80% (unitária), ~0% (integração sem dados reais)
**Principais forças:** Boa separação unitário/integração, mocks corretos sem I/O real, testes de contrato de schema (todas as chaves obrigatórias), isolamento de exceções testado explicitamente.
**Principais lacunas:** `_extract_contacts` e `_extract_document` do WHOIS não testados, polling loop do FaceCheck, `_render_investigate_item` com dados reais.

---

## Consolidado de Sugestões por Prioridade

### Alta — risco funcional ou de dados

| Item | Arquivo | Descrição |
|------|---------|-----------|
| 1 | `dossie_generator.py:122` | `.replace("Violação N", "Investigação N")` pode corromper documento se dados contiverem essa string. Refatorar para passar label como parâmetro. |
| 2 | `ui/app.py:123` | Ausência de try/except em `_run_async(search_image(...))` causa traceback bruto na tela do usuário. |
| 3 | `export/pdf_exporter.py` | Ausência de tratamento de erro em `to_bytes()` propaga exceção do WeasyPrint sem mensagem amigável. |

### Média — qualidade e manutenção

| Item | Arquivo | Descrição |
|------|---------|-----------|
| 4 | `lookup/orchestrator.py:108` | Re-import dinâmico de `lookup_jucesp` desnecessário — usar o import do topo. |
| 5 | `lookup/orchestrator.py:128` | `_no_cnpj_result` é `async` sem nenhum `await` — tornar síncrona. |
| 6 | `lookup/cnpj_client.py` | `_not_found_result` e `_error_result` com schema idêntico — unificar para eliminar repetição. |
| 7 | `ui/app.py:171` | `_passes_filter` redefinida a cada rerun — mover para escopo de módulo. |
| 8 | `ui/app.py:286` | Conflito de nome de variável `domain` entre curadoria e exportação. |

### Baixa — melhoria incremental

| Item | Arquivo | Descrição |
|------|---------|-----------|
| 9 | `lookup/jucesp_client.py` | Gerar URL de busca com nome da empresa pré-preenchido (ex: `?q=Empresa+Ltda`) para agilizar revisão manual do Ulysses. |
| 10 | `search/aggregator.py` | `_extract_domain` duplicado em 3 arquivos — candidato a `src/utils.py` se houver mais funções compartilhadas. |
| 11 | `tests/conftest.py` | Adicionar fixtures compartilhadas para reduzir duplicação de `_make_*` entre arquivos de teste. |
| 12 | `tests/test_lookup.py` | Adicionar teste para `_extract_contacts` e `_extract_document` com texto WHOIS real. |
| 13 | `ui/app.py:229` | Bug cosmético: label `"✅ *Violação*"` usa asteriscos de itálico Markdown que não são renderizados em labels de botão Streamlit — aparecem como `*Violação*` literal. Remover os asteriscos. |
| 14 | `tests/test_export.py:19` | `sys.path.insert` manual indica ausência de `pip install -e .` — frágil em outros ambientes. |
| 15 | `tests/test_export.py` | `test_to_bytes_returns_bytes` apenas verifica `isinstance(result, bytes)` — não confirma PDF válido. Adicionar `assert result[:4] == b"%PDF"`. |

---

*Relatório gerado por revisão estática em 2026-03-18.*
