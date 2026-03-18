# POC — Orquestrador de APIs Jurídicas

## O que é este projeto

Sistema que recebe a foto de um cliente, roda busca facial + busca reversa de imagem em paralelo via APIs, puxa dados do responsável (CNPJ + WHOIS) automaticamente e exporta um dossiê estruturado — substituindo 2–4h de trabalho manual do advogado entre 4–6 ferramentas separadas.

**Usuário único na POC:** Ulysses — advogado especialista em direito de imagem.

---

## Stack definido (não alterar sem aprovação)

| Função | API | Custo |
|--------|-----|-------|
| Busca facial | FaceCheck.ID | Free (modo teste) |
| Busca reversa | Google Vision Web Detection | Free (1.000/mês + $300 crédito) |
| Dados do responsável | WHOIS lookup + Receita Federal (CNPJ) | Free |
| Contrato social | JUCESP (apenas SP na POC) | Free |
| Exportação | Markdown ou PDF | — |

**Fora do escopo da POC:** PimEyes, TinEye, Bing Visual Search, certificação blockchain (Verifact), autenticação multi-usuário, modo proativo (mineração em lote).

---

## Fluxo principal

```
1. Upload da foto do cliente
2. Busca em paralelo: FaceCheck.ID (facial) + Google Vision Web Detection (reversa)
3. Agregação e deduplicação dos resultados
4. Para cada domínio encontrado: WHOIS + CNPJ (Receita Federal) automaticamente
5. Interface de curadoria: advogado marca cada resultado como violação / não-violação / investigar
6. Exportação do dossiê (apenas resultados marcados como violação)
```

---

## Critérios de sucesso da POC

- **Hipótese 1 (busca):** recall ≥ 70% das violações + tempo ≤ 30 min por caso
- **Hipótese 2 (responsável):** ≥ 70% dos lookups retornam CNPJ + razão social sem intervenção manual
- **Hipótese 3 (dossiê):** ≥ 60% dos dossiês adotados por Ulysses sem edição estrutural

---

## Estrutura de pastas

```
projeto-alpha/                        ← raiz do projeto de produto
├── 01-discovery/poc-shaping.md       ← escopo e decisões de produto
├── 01-discovery/poc-validation.md    ← critérios de sucesso e kill signals
├── 01-discovery/jtbd.md              ← jobs-to-be-done do Ulysses
└── poc-orquestrador/                 ← repositório técnico da POC (você está aqui)
    ├── CLAUDE.md              ← este arquivo — leia sempre primeiro
    ├── specs/poc-tecnica.md   ← arquitetura e sequência de build
    ├── ai_docs/               ← documentação das APIs (facecheck, google vision)
    ├── src/                   ← código da aplicação
    └── .claude/commands/      ← slash commands reutilizáveis
```

---

## Boas práticas de codificação com Claude (leia uma vez ao iniciar)

Este projeto segue as boas práticas extraídas de experts em Claude Code. O documento completo está em:
`../referencias/transcricoes/analise-completa-claude-code.md`

Resumo dos princípios que regem este repositório:
- Planejar antes de codar (`specs/` → Plan Mode → execução)
- Context Priming: carregar só o que a tarefa exige
- Validação determinística após cada entrega (`/test`)
- Agentes focados em um propósito, nunca generalistas
- Refatoração cirúrgica (~50 linhas por vez, nunca "refatore tudo")

---

## Documentação de contexto (leia sob demanda, não automaticamente)

Esta POC está dentro do projeto `projeto-alpha/`. Os documentos de produto originais ficam um nível acima:

| Arquivo | Quando ler |
|---------|-----------|
| `../01-discovery/poc-shaping.md` | Para entender escopo, rabbit holes e decisões de produto |
| `../01-discovery/poc-validation.md` | Para entender critérios de sucesso e kill signals de cada hipótese |
| `../01-discovery/jtbd.md` | Para entender o fluxo de trabalho do Ulysses e o que ele precisa no dossiê |

> Carregue esses arquivos apenas quando a tarefa exigir — não em todo prompt.

---

## Regras de trabalho (não negociáveis)

1. **Leia specs/poc-tecnica.md antes de qualquer implementação.** Nunca crie arquivos ou escreva código sem um plano aprovado na pasta specs/.
2. **Use Plan Mode (Shift+Tab) para planejar, Auto-Accept para executar.** Nunca misture os dois.
3. **Implemente uma hipótese por vez**, na sequência: Hipótese 2 → Hipótese 1 → Hipótese 3.
4. **Nenhum dado de casos ativos de Ulysses** deve ser usado em testes — apenas casos encerrados.
5. **Quando um dado de empresa for incerto** (CNPJ não encontrado, WHOIS incompleto), sinalize explicitamente ao usuário — nunca assuma silenciosamente.
6. **O dossiê exportado nunca decide o que é violação** — apenas organiza o que o advogado marcou.
7. **Prefira funções pequenas e focadas.** Nada de arquivos com mais de 300 linhas sem uma refatoração cirúrgica aprovada.
8. **Após cada entrega funcional**, rode os testes definidos em specs/poc-tecnica.md antes de avançar.

---

## Contexto de produto (leia para entender as decisões)

- O advogado é o middleware humano entre ferramentas que não se falam — o produto é a cola.
- O julgamento de "o que é violação" é insubstituível por automação — o sistema classifica e destaca, a decisão é do advogado.
- A cadeia de custódia das provas é sagrada — nada pode comprometer a robustez jurídica.
- Google Drive é o backbone atual do Ulysses — o dossiê exportado precisa ser compatível.
