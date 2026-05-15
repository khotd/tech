"""События в RabbitMQ (Celery использует Redis)."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("dating_backend")


def publish_dating_event(event_type: str, payload: Dict[str, Any]) -> None:
    try:
        import pika
    except ImportError:
        return

    from config import RABBITMQ_QUEUE, RABBITMQ_URL

    body = {
        "type": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        ch.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
        ch.basic_publish(
            exchange="",
            routing_key=RABBITMQ_QUEUE,
            body=raw,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        conn.close()
    except Exception as exc:
        logger.warning("RabbitMQ publish skipped: %s", exc)
