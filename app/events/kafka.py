import json
import logging

from aiokafka import AIOKafkaProducer # type: ignore

from app.api.utils.common import common_logger

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(bootstrap_servers="localhost:9092")
        await _producer.start()
    return _producer


async def shutdown_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish_kafka_event(topic: str, payload: dict) -> None:
    producer = await get_producer()
    try:
        await producer.send_and_wait(topic, value=json.dumps(payload).encode("utf-8"))
        common_logger(f"[KAFKA] topic={topic!r} payload={payload}", level="info")
    except Exception as exc:
        logger.error("Failed to publish Kafka event to %r", topic, exc_info=exc)
