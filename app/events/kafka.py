import json
import logging
import os

from aiokafka import AIOKafkaProducer # type: ignore

from app.api.utils.common import common_logger

logger = logging.getLogger(__name__)

_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        candidate = AIOKafkaProducer(bootstrap_servers=_BOOTSTRAP_SERVERS)
        await candidate.start()  # if this raises, _producer stays None so the next call retries
        _producer = candidate
    return _producer


async def shutdown_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish_kafka_event(topic: str, payload: dict) -> None:
    # The document is already durably written to S3 + Postgres by the time this is
    # called — a broker outage here should degrade (event lost, doc stuck until
    # reconciled) rather than fail the whole upload request with a 500.
    try:
        producer = await get_producer()
        await producer.send_and_wait(topic, value=json.dumps(payload).encode("utf-8"))
        common_logger(f"[KAFKA] topic={topic!r} payload={payload}", level="info")
    except Exception as exc:
        logger.error("Failed to publish Kafka event to %r", topic, exc_info=exc)
