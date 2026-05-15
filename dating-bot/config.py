import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///dating_bot.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "dating.events")

USE_MINIO = os.getenv("USE_MINIO", "false").lower() in ("1", "true", "yes")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "dating-photos")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
MINIO_PUBLIC_BASE = os.getenv("MINIO_PUBLIC_BASE", "").rstrip("/")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


def get_sync_database_url() -> str:
    explicit = os.getenv("API_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    root = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(root, "dating_bot.db")
    return "sqlite:///" + os.path.abspath(path).replace("\\", "/")