# /test — Rodar testes e validar entrega

Antes de marcar qualquer tarefa como concluída:

1. Identifique qual módulo foi implementado (lookup / search / export / ui)
2. Rode os testes correspondentes:
   - Lookup: `python -m pytest tests/test_lookup.py -v`
   - Search: `python -m pytest tests/test_search.py -v`
   - Export: `python -m pytest tests/test_export.py -v`
3. Se algum teste falhar:
   - Leia o erro completo
   - Corrija o código (não o teste)
   - Rode novamente até passar
4. Reporte o resultado no formato:

```
## Resultado dos testes

**Módulo:** [lookup / search / export]
**Passou:** X/Y
**Falhou:** Z/Y

### Falhas (se houver)
- teste_xyz: [motivo]

### Ação tomada
- [o que foi corrigido]
```

5. Atualize o checkbox correspondente em `specs/poc-tecnica.md` somente após todos os testes passarem.
