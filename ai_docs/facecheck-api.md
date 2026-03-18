# FaceCheck.ID — API Reference

**Base URL:** `https://facecheck.id`
**Auth:** Header `Authorization: YOUR_API_TOKEN` (sem prefixo "Bearer")

---

## Fluxo obrigatório (2 etapas)

A busca é assíncrona — precisa de upload primeiro, depois polling até conclusão.

```
1. POST /api/upload_pic   → recebe id_search
2. POST /api/search       → polling até output != null
```

---

## Endpoint 1 — Upload da imagem

**POST** `/api/upload_pic`
**Content-Type:** `multipart/form-data`

### Request

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `images` | file | sim | Arquivo de imagem a analisar |
| `id_search` | string | não | Identificador de busca existente (reutilização) |

### Response

```json
{
  "error": null,
  "code": "string",
  "id_search": "abc123",
  "message": "Image uploaded successfully"
}
```

Se `error != null`, abortar com `f"{error} ({code})"`.

---

## Endpoint 2 — Executar busca (polling)

**POST** `/api/search`
**Content-Type:** `application/json`

### Request

```json
{
  "id_search": "abc123",
  "with_progress": true,
  "status_only": false,
  "demo": false
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_search` | string | ID retornado pelo upload |
| `with_progress` | bool | Incluir percentual de progresso na resposta |
| `status_only` | bool | Retornar só status sem resultados (mais leve) |
| `demo` | bool | Modo teste: escaneia só 100.000 faces, sem deduzir créditos, menor precisão |

### Response — em progresso

```json
{
  "error": null,
  "code": "string",
  "message": "Searching...",
  "progress": 45,
  "output": null
}
```

### Response — concluído

```json
{
  "error": null,
  "code": "string",
  "message": "Search complete",
  "progress": 100,
  "output": {
    "items": [
      {
        "guid": "string",
        "score": 87,
        "base64": "data:image/jpeg;base64,...",
        "url": "https://example.com/page-where-face-was-found",
        "index": 0
      }
    ]
  }
}
```

### Campos de cada item

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `guid` | string | Identificador único do resultado |
| `score` | int (0–100) | Similaridade da face encontrada |
| `base64` | string | Thumbnail codificada em base64 |
| `url` | string | URL da página onde a face foi encontrada |
| `index` | int | Posição no ranking |

---

## Créditos e pricing

- Cada busca consome **3 créditos**
- Preço: **$0.10 USD por crédito**
- Pagamento: criptomoeda (Bitcoin, Litecoin)
- Contas trial: **200 TrialSearches** gratuitas
- Modo `demo: true`: sem dedução de créditos (uso em testes)

---

## Exemplo Python completo

```python
import time
import requests

TESTING_MODE = True  # False em produção
APITOKEN = 'YOUR_API_TOKEN'

def search_by_face(image_file: str) -> tuple[str | None, list | None]:
    if TESTING_MODE:
        print('*** TESTING MODE — resultados imprecisos, créditos NÃO deduzidos ***')

    site = 'https://facecheck.id'
    headers = {'accept': 'application/json', 'Authorization': APITOKEN}

    # Passo 1: upload
    files = {'images': open(image_file, 'rb'), 'id_search': None}
    response = requests.post(site + '/api/upload_pic', headers=headers, files=files).json()

    if response['error']:
        return f"{response['error']} ({response['code']})", None

    id_search = response['id_search']
    print(f"Upload OK — id_search={id_search}")

    # Passo 2: polling
    json_data = {
        'id_search': id_search,
        'with_progress': True,
        'status_only': False,
        'demo': TESTING_MODE,
    }

    while True:
        response = requests.post(site + '/api/search', headers=headers, json=json_data).json()
        if response['error']:
            return f"{response['error']} ({response['code']})", None
        if response['output']:
            return None, response['output']['items']
        print(f"Progresso: {response['progress']}% — {response['message']}")
        time.sleep(1)


# Uso
error, items = search_by_face("foto.jpg")

if items:
    for item in items:
        print(f"score={item['score']} url={item['url']}")
else:
    print(f"Erro: {error}")
```

---

## Observações para a POC

- Polling com `time.sleep(1)` — adaptar para `asyncio.sleep(1)` na versão async
- `score` é a principal métrica de relevância; scores < 50 são menos confiáveis
- `url` é a página onde a imagem foi encontrada — usar para lookup WHOIS/CNPJ
- `base64` serve como thumbnail no dossiê (não precisa re-baixar a imagem)
- Em produção, `demo: false` e créditos reais
