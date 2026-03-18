# /status — Diagnóstico do estado atual da POC

Execute este diagnóstico e retorne um resumo claro:

1. Leia `specs/poc-tecnica.md` e verifique os checkboxes de cada fase
2. Liste os arquivos existentes em `src/` e `tests/`
3. Identifique:
   - Qual hipótese está em andamento
   - O que foi concluído
   - O que está pendente
   - Se há algum bloqueio (credencial faltando, dado não encontrado, teste falhando)
4. Retorne no formato:

```
## Status da POC

**Fase atual:** [H2 / H1 / H3]
**Progresso:** [X de Y tarefas concluídas]

### Concluído ✅
- ...

### Em andamento 🔄
- ...

### Bloqueios ⚠️
- ...

### Próxima ação recomendada
- ...
```
