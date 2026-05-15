"""Чтение очереди RabbitMQ. Запуск: python -m backend.event_consumer"""
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dating_consumer")


def main():
    sys.path.insert(0, ".")
    import pika
    from config import RABBITMQ_QUEUE, RABBITMQ_URL

    params = pika.URLParameters(RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    logger.info("Listening on queue %s", RABBITMQ_QUEUE)

    def on_message(_ch, method, _properties, body):
        try:
            data = json.loads(body.decode("utf-8"))
            logger.info("event=%s payload=%s", data.get("type"), data.get("payload"))
        except Exception as exc:
            logger.exception("Bad message: %s", exc)
        finally:
            _ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=20)
    ch.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=on_message)
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    conn.close()
    logger.info("Consumer stopped")


if __name__ == "__main__":
    main()
