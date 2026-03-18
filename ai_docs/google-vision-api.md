# Google Cloud Vision API — Web Detection Reference

**Endpoint:** `POST https://vision.googleapis.com/v1/images:annotate`
**Feature type:** `WEB_DETECTION`
**Lib Python:** `google-cloud-vision`

---

## Autenticação

Duas opções:

**Opção 1 — API Key (mais simples para POC)**
```
GET/POST ...?key=GOOGLE_CLOUD_API_KEY
```

**Opção 2 — Service Account (recomendado para produção)**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"
```
```python
from google.cloud import vision
client = vision.ImageAnnotatorClient()  # usa ADC automaticamente
```

---

## Request — REST (API Key)

**POST** `https://vision.googleapis.com/v1/images:annotate?key=API_KEY`
**Content-Type:** `application/json`

```json
{
  "requests": [
    {
      "image": {
        "content": "BASE64_ENCODED_IMAGE_BYTES"
      },
      "features": [
        {
          "type": "WEB_DETECTION",
          "maxResults": 10
        }
      ]
    }
  ]
}
```

Alternativa com URL pública (sem base64):
```json
{
  "image": {
    "source": {
      "imageUri": "https://example.com/image.jpg"
    }
  }
}
```

---

## Response — estrutura completa

```json
{
  "responses": [
    {
      "webDetection": {
        "webEntities": [
          {
            "entityId": "/m/02p7_j8",
            "score": 1.44,
            "description": "Carnival in Rio de Janeiro"
          }
        ],
        "fullMatchingImages": [
          { "url": "https://example.com/exact-match.jpg" }
        ],
        "partialMatchingImages": [
          { "url": "https://example.com/partial-match.jpg" }
        ],
        "pagesWithMatchingImages": [
          {
            "url": "https://example.com/page",
            "pageTitle": "Example Page Title",
            "fullMatchingImages": [
              { "url": "https://example.com/image-on-page.jpg" }
            ],
            "partialMatchingImages": [
              { "url": "https://example.com/similar-on-page.jpg" }
            ]
          }
        ],
        "visuallySimilarImages": [
          { "url": "https://example.com/visually-similar.jpg" }
        ],
        "bestGuessLabels": [
          {
            "label": "rio carnival",
            "languageCode": "en"
          }
        ]
      }
    }
  ]
}
```

### Campos relevantes para a POC

| Campo | Uso |
|-------|-----|
| `pagesWithMatchingImages[].url` | Domínio da violação — entrada para WHOIS/CNPJ |
| `pagesWithMatchingImages[].pageTitle` | Título da página para o dossiê |
| `fullMatchingImages[].url` | URL exata da imagem encontrada |
| `visuallySimilarImages[].url` | Imagens similares (busca mais ampla) |
| `webEntities[].description` | Contexto semântico da imagem |

---

## Exemplo Python — imagem local (SDK)

```python
def detect_web(path: str) -> dict:
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    with open(path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)
    response = client.web_detection(image=image)

    if response.error.message:
        raise Exception(response.error.message)

    annotations = response.web_detection
    results = []

    for page in annotations.pages_with_matching_images:
        results.append({
            "page_url": page.url,
            "page_title": page.page_title,
            "full_matches": [img.url for img in page.full_matching_images],
            "partial_matches": [img.url for img in page.partial_matching_images],
        })

    return {
        "pages": results,
        "visually_similar": [img.url for img in annotations.visually_similar_images],
        "web_entities": [
            {"description": e.description, "score": e.score}
            for e in annotations.web_entities
        ],
        "best_guess": [l.label for l in annotations.best_guess_labels],
    }
```

## Exemplo Python — imagem por URL (SDK)

```python
def detect_web_uri(uri: str) -> dict:
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    image = vision.Image()
    image.source.image_uri = uri

    response = client.web_detection(image=image)

    if response.error.message:
        raise Exception(response.error.message)

    annotations = response.web_detection
    # mesma estrutura de retorno acima
```

## Exemplo Python — REST com API Key (sem SDK, via httpx)

```python
import base64
import httpx

async def detect_web_rest(image_path: str, api_key: str) -> dict:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": image_b64},
                "features": [{"type": "WEB_DETECTION", "maxResults": 20}],
            }
        ]
    }

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

    data = response.json()
    return data["responses"][0].get("webDetection", {})
```

---

## Rate limits e pricing

| Tier | Limite |
|------|--------|
| Gratuito | 1.000 unidades/mês |
| Após cota gratuita | ~$1.50 por 1.000 unidades |
| Batch request | Até 2.000 imagens por request |

- Cada imagem = 1 unidade (`WEB_DETECTION`)
- $300 de crédito gratuito no Google Cloud (novos usuários)

---

## Instalação

```bash
pip install google-cloud-vision
```

Ou, sem SDK (só httpx):
```bash
# nenhuma lib extra — usar REST direto com GOOGLE_CLOUD_API_KEY
```

---

## Observações para a POC

- **Preferir REST com API Key** (`GOOGLE_CLOUD_API_KEY`) — evita setup de service account para a POC
- `pagesWithMatchingImages` é a fonte primária de domínios para lookup WHOIS/CNPJ
- `visuallySimilarImages` amplia o recall mas pode trazer falsos positivos — filtrar por score/domínio
- Enviar imagem como base64 (arquivo local do Ulysses) em vez de URL pública
- `maxResults: 20` é um bom ponto de partida; aumentar se recall for baixo
