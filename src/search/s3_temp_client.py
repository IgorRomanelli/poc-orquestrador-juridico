"""
Cliente S3 temporário — hospedagem segura de imagem para obter presigned URL.

Necessário porque SerpAPI aceita apenas image_url, não upload direto.
A imagem fica em bucket S3 privado com presigned URL de 60 segundos.
O objeto é deletado após o uso.

Variáveis de ambiente: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
                       AWS_REGION (default: us-east-1), AWS_S3_BUCKET
"""

import os
import uuid

import boto3
from dotenv import load_dotenv

load_dotenv()

_BUCKET = os.getenv("AWS_S3_BUCKET", "")
_REGION = os.getenv("AWS_REGION", "us-east-1")
_EXPIRATION_SECONDS = 60


def _get_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=_REGION,
    )


def upload_and_get_url(image_bytes: bytes) -> tuple[str, str]:
    """
    Faz upload de imagem para S3 e retorna (presigned_url, s3_key).

    Args:
        image_bytes: bytes da imagem em formato JPEG.

    Returns:
        Tupla (url, key) onde url expira em 60 segundos.

    Raises:
        RuntimeError: se AWS_S3_BUCKET não configurado.
    """
    if not _BUCKET:
        raise RuntimeError("AWS_S3_BUCKET não configurado — configure no .env")

    key = f"temp-search/{uuid.uuid4()}.jpg"
    client = _get_client()

    client.put_object(
        Bucket=_BUCKET,
        Key=key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_EXPIRATION_SECONDS,
    )

    return url, key


def delete_object(key: str) -> None:
    """Remove objeto do bucket S3 após o uso."""
    client = _get_client()
    client.delete_object(Bucket=_BUCKET, Key=key)
