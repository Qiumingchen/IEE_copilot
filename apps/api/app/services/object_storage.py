from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from minio import Minio

from app.core.config import get_settings


def store_structure_file(
    *,
    file_name: str,
    content: bytes,
    content_type: str | None,
) -> dict[str, str | int | None]:
    settings = get_settings()
    safe_name = Path(file_name).name.replace("\\", "_").replace("/", "_")
    object_key = f"structures/{uuid4()}/{safe_name}"
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    client.put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(content),
        length=len(content),
        content_type=content_type or "application/octet-stream",
    )
    return {
        "bucket": settings.minio_bucket,
        "object_key": object_key,
        "checksum": sha256(content).hexdigest(),
        "content_type": content_type,
        "size_bytes": len(content),
    }


def read_structure_file(*, object_key: str) -> bytes:
    settings = get_settings()
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    response = client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
