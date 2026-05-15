"""MinIO (S3 API) для фото."""
import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Optional, Tuple

logger = logging.getLogger("dating_backend")


def _client():
    from minio import Minio
    from config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE

    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_bucket() -> None:
    from config import MINIO_BUCKET, USE_MINIO

    if not USE_MINIO:
        return
    client = _client()
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)


def upload_telegram_photo_bytes(
    data: bytes, content_type: str = "image/jpeg"
) -> Tuple[str, str]:
    from config import MINIO_BUCKET, MINIO_PUBLIC_BASE, MINIO_ENDPOINT, MINIO_SECURE

    ensure_bucket()
    key = f"photos/{uuid.uuid4().hex}.jpg"
    client = _client()
    client.put_object(
        MINIO_BUCKET,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    if MINIO_PUBLIC_BASE:
        public_url = f"{MINIO_PUBLIC_BASE}/{MINIO_BUCKET}/{key}"
    else:
        scheme = "https" if MINIO_SECURE else "http"
        public_url = f"{scheme}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}"
    return key, public_url


def fetch_telegram_file_bytes(bot_token: str, file_id: str) -> Optional[Tuple[bytes, str]]:
    try:
        meta_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={urllib.parse.quote(file_id)}"
        with urllib.request.urlopen(meta_url, timeout=20) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        if not j.get("ok"):
            logger.error("getFile failed: %s", j)
            return None
        path = j["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{path}"
        with urllib.request.urlopen(file_url, timeout=60) as fr:
            data = fr.read()
            ct = fr.headers.get("Content-Type", "image/jpeg")
        return data, ct
    except Exception as exc:
        logger.exception("Telegram file download failed: %s", exc)
        return None
