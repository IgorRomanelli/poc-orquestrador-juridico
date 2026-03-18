"""
Cliente Amazon Rekognition — verificação de similaridade facial.

Usa CompareFaces para verificar se o rosto numa imagem encontrada
corresponde ao rosto da foto original do cliente.

Função pública:
    compare_faces(source_bytes, target_bytes) → dict
        status: "found" | "not_found" | "error"
        similarity: float (0–1) ou None
"""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
_AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")
_AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_is_configured: bool = bool(_AWS_KEY and _AWS_SECRET)


def _get_client():
    return boto3.client(
        "rekognition",
        region_name=_AWS_REGION,
        aws_access_key_id=_AWS_KEY,
        aws_secret_access_key=_AWS_SECRET,
    )


def compare_faces(source_bytes: bytes, target_bytes: bytes) -> dict:
    """
    Compara rosto da imagem-fonte com rosto da imagem-alvo.

    Args:
        source_bytes: bytes da foto do cliente (imagem de referência).
        target_bytes: bytes da imagem encontrada nos resultados.

    Returns:
        dict com:
            status     : "found" | "not_found" | "error"
            similarity : float 0–1 se found, None caso contrário
            message    : descrição do erro (apenas quando status="error")
    """
    if not _is_configured:
        return {"status": "error", "similarity": None, "message": "credenciais AWS não configuradas"}

    try:
        client = _get_client()
        response = client.compare_faces(
            SourceImage={"Bytes": source_bytes},
            TargetImage={"Bytes": target_bytes},
            SimilarityThreshold=0,
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        return {"status": "error", "similarity": None, "message": f"Rekognition {code}: {msg}"}
    except (BotoCoreError, Exception) as exc:
        return {"status": "error", "similarity": None, "message": f"Rekognition erro: {exc}"}

    matches = response.get("FaceMatches", [])
    if not matches:
        return {"status": "not_found", "similarity": None, "message": None}

    best = max(matches, key=lambda m: m.get("Similarity", 0))
    similarity = round(best["Similarity"] / 100, 4)
    return {"status": "found", "similarity": similarity, "message": None}
