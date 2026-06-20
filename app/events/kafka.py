from app.api.utils.common import common_logger


async def publish_kafka_event(topic: str, payload: dict) -> None:
    # TODO: replace with a real Kafka producer (e.g. aiokafka AIOKafkaProducer)
    common_logger(f"[KAFKA STUB] topic={topic!r} payload={payload}", level="warning")
