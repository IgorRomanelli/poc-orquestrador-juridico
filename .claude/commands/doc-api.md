# /doc-api — Documentar uma API antes de integrá-la

Argumento: $arguments (nome da API — ex: "facecheck" ou "google-vision")

Antes de escrever qualquer client de API:

1. Pesquise (via web ou documentação fornecida) os seguintes pontos sobre a API "$arguments":
   - URL base dos endpoints relevantes
   - Formato de autenticação (API key, OAuth, Bearer)
   - Formato da requisição (multipart para imagem? JSON? URL?)
   - Formato da resposta (campos retornados, tipos)
   - Rate limits e quotas do plano gratuito
   - Códigos de erro mais comuns e como tratá-los

2. Salve o resultado em `ai_docs/$arguments-api.md` com o formato:

```markdown
# API: [nome]
**Documentado em:** [data]

## Endpoint principal
...

## Autenticação
...

## Formato da requisição
...

## Formato da resposta
...

## Rate limits
...

## Tratamento de erros
...

## Exemplo de uso (curl)
...
```

3. Confirme com o usuário antes de iniciar a implementação do client.
