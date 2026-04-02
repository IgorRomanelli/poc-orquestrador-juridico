# Spec Técnica — POC Orquestrador de APIs Jurídicas

**Data:** 2026-03-18
**Base:** poc-shaping.md + poc-validation.md + JTBD (Ulysses)
**Status:** Pronto para implementação

---

## Arquitetura geral

```
┌─────────────────────────────────────────────────────┐
│                   Interface Web                     │
│   (upload de foto + curadoria + exportação)         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Orquestrador (backend)                 │
│                                                     │
│   ┌──────────────┐      ┌──────────────────────┐   │
│   │  FaceCheck   │      │  Google Vision Web   │   │
│   │  (facial)    │      │  Detection (reversa) │   │
│   └──────┬───────┘      └──────────┬───────────┘   │
│          └──────────┬──────────────┘               │
│               ┌─────▼──────┐                       │
│               │ Agregador  │                       │
│               │ + Dedup    │                       │
│               └─────┬──────┘                       │
│                     │                              │
│            ┌────────▼────────┐                     │
│            │  Lookup Worker  │                     │
│            │ WHOIS + CNPJ +  │                     │
│            │ JUCESP (SP)     │                     │
│            └────────┬────────┘                     │
└─────────────────────┼───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│           Curadoria + Exportação                    │
│   (UI: marcar violação / não / investigar)          │
│   (output: dossiê markdown ou PDF)                  │
└─────────────────────────────────────────────────────┘
```

---

## Stack técnico recomendado

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| Backend | Python (FastAPI) | Excelente para orquestração de APIs assíncronas; fácil de testar |
| Frontend | HTML + HTMX ou Streamlit | Mínimo para a POC — sem framework pesado |
| Async | asyncio + httpx | Chamadas paralelas às APIs |
| Exportação | markdown-pdf ou WeasyPrint | Dossiê em PDF |
| Ambiente | .env para credenciais | Nunca commitar chaves |

> **Nota para o Claude:** Sugira Streamlit se precisar de uma UI funcional rápida. Use FastAPI se a separação backend/frontend for importante. Pergunte ao usuário antes de decidir.

---

## Sequência de implementação (siga esta ordem)

### Fase 1 — Hipótese 2: Lookup do responsável
> **Por que primeiro:** É a mais rápida de construir, resultado binário claro, não depende das APIs de busca de imagem.

**Entregável:** Script Python que recebe um domínio e retorna CNPJ + razão social + endereço + responsável.

**Tarefas:**
- [x] `src/lookup/whois_client.py` — consulta WHOIS de um domínio
- [x] `src/lookup/cnpj_client.py` — consulta Receita Federal via receitaws (sem token, JSON limpo)
- [x] `src/lookup/jucesp_client.py` — gera link direto JUCESP + flag manual_required (scraping desproporcional para Fase 1)
- [x] `src/lookup/orchestrator.py` — chama os 3 em paralelo para um domínio; Passo 1c integrado
- [x] `src/lookup/domain_id_client.py` — identifica operador de domínios `.com` via crt.sh (subject_o) → Netlas WHOIS histórico → pending; acionado quando WHOIS/RDAP não retorna registrante útil
- [x] `tests/test_lookup.py` — 46 testes unitários passando
- [ ] Critério de parada: > 30% exigir intervenção manual → parar e revisar

**Comportamento obrigatório quando dado não encontrado:**
```python
# NUNCA retornar silenciosamente None ou string vazia
# SEMPRE retornar estrutura explícita:
{
  "domain": "exemplo.com.br",
  "cnpj": None,
  "razao_social": None,
  "status": "not_found",  # ou "error" ou "found"
  "requires_manual_review": True,
  "message": "CNPJ não encontrado — validar manualmente"
}
```

---

### Fase 2 — Hipótese 1: Busca unificada de imagem
> **Depende de:** credenciais FaceCheck.ID + Google Cloud Vision API configuradas.

**Entregável:** Endpoint que recebe uma imagem e retorna lista unificada de resultados com preview + link + domínio.

**Tarefas:**
- [x] `ai_docs/facecheck-api.md` — documentar endpoints, rate limits e formato de resposta do FaceCheck
- [x] `ai_docs/google-vision-api.md` — documentar endpoints, rate limits e formato de resposta do Google Vision
- [x] `src/search/facecheck_client.py` — client para FaceCheck.ID
- [x] `src/search/google_vision_client.py` — client para Google Vision Web Detection
- [x] `src/search/serper_client.py` — Google Lens via Serper (busca reversa por URL)
- [x] `src/search/searchapi_client.py` — Google Lens via SearchAPI (busca reversa por URL, redundância)
- [x] `src/search/copyseeker_client.py` — busca reversa visual via RapidAPI; retorna páginas com a imagem
- [x] `src/search/rekognition_client.py` — Amazon Rekognition CompareFaces; enriquece confidence dos resultados sem score nativo
- [x] `src/search/s3_temp_client.py` — upload temporário da imagem para S3; gera presigned URL usada pelos clientes de URL
- [x] `src/search/aggregator.py` — agrega + deduplica resultados das múltiplas fontes; enriquecimento Rekognition
- [x] `src/search/orchestrator.py` — chama FaceCheck + Google Vision em paralelo (asyncio)
- [x] `src/search/full_search.py` — orquestra as 4 fontes em paralelo via S3 presigned URL; deduplicação global; Rekognition opcional
- [x] `tests/test_search.py` — testes unitários passando
- [ ] Critério de parada: recall < 70% em mais de 2 dos 5 casos → revisar stack

**Estrutura do resultado agregado:**
```python
{
  "results": [
    {
      "image_url": "https://...",
      "page_url": "https://...",
      "domain": "exemplo.com.br",
      "source": "facecheck" | "google_vision",
      "confidence": 0.87,  # se disponível
      "preview_thumbnail": "https://..."
    }
  ],
  "total": 24,
  "deduplicated": 18,
  "search_time_seconds": 12.4
}
```

---

### Fase 3 — Hipótese 3: Dossiê estruturado
> **Depende de:** Fases 1 e 2 funcionando.

**Entregável:** Interface de curadoria + exportação do dossiê.

**Tarefas:**
- [x] `web/` — interface Next.js (substituiu Streamlit); deploy no Vercel
  - Upload de foto + busca assíncrona com polling
  - Tela de resumo (Alta / Média / Baixa confiança)
  - Grade de resultados estática (pré-validação de thumbnails); seção Inconclusivos colapsável
  - Curadoria: marcar violação por card; selecionar todos; ActionBar com progresso
  - Tela de análise com dados de lookup (CNPJ, WHOIS, responsáveis)
  - Exportação do dossiê em PDF
- [x] `src/export/dossie_generator.py` — gera markdown estruturado com apenas os resultados marcados como violação
- [x] `src/export/pdf_exporter.py` — converte markdown em PDF
- [x] `tests/test_export.py` — validar formato do dossiê
- [x] Deploy backend no Railway; deploy frontend no Vercel
- [ ] Critério de parada: > 40% dos casos exigirem edição estrutural → reprojetar estrutura do dossiê

**Estrutura do dossiê exportado:**
```markdown
# Dossiê de Violação de Imagem
**Cliente:** [nome]
**Data:** [data]
**Gerado por:** [sistema]

---

## Violações Identificadas

### Violação 1
- **URL:** https://...
- **Domínio:** exemplo.com.br
- **Empresa responsável:** Exemplo Ltda
- **CNPJ:** 00.000.000/0001-00
- **Responsável:** João da Silva
- **WHOIS:** exemplo.com.br / registrado em 2020
- **Preview:** [imagem]

[... demais violações ...]

---

## Resultados para Investigação

[resultados marcados como "investigar"]

---
*Dossiê gerado automaticamente. Curadoria realizada por [advogado] em [data].*
```

---

## Credenciais necessárias (configurar antes de iniciar)

Criar arquivo `.env` na raiz (nunca commitar):

```env
FACECHECK_API_KEY=sua_chave_aqui
GOOGLE_APPLICATION_CREDENTIALS=path/para/credentials.json
# ou
GOOGLE_CLOUD_API_KEY=sua_chave_aqui
```

---

## Testes com dados reais

| Hipótese | Dataset | Critério de sucesso |
|----------|---------|---------------------|
| H2 (lookup) | 10 domínios de casos encerrados | ≥ 70% sem intervenção manual |
| H1 (busca) | 5 casos encerrados com dossiê original | Recall ≥ 70% |
| H3 (dossiê) | 5 casos novos com Ulysses presente | ≥ 60% sem edição estrutural |

**Guardrail:** Nunca usar dados de casos ativos. Apenas casos encerrados com resultado já conhecido.

---

## Arquivos a criar (visão geral)

```
src/
├── lookup/
│   ├── whois_client.py
│   ├── cnpj_client.py
│   ├── jucesp_client.py
│   └── orchestrator.py
├── search/
│   ├── facecheck_client.py
│   ├── google_vision_client.py
│   ├── aggregator.py
│   └── orchestrator.py
├── export/
│   ├── dossie_generator.py
│   └── pdf_exporter.py
└── ui/
    └── app.py  (Streamlit ou FastAPI + templates)

tests/
├── test_lookup.py
├── test_search.py
└── test_export.py

ai_docs/
├── facecheck-api.md
└── google-vision-api.md

.env  (não commitar — adicionar ao .gitignore)
requirements.txt
```
