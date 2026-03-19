# kafka_client.py — Kafka producer singleton with graceful degradation
import json

from logging_config import get_logger

logger = get_logger("kafka_client")

# Module-level singleton — lazy-initialized
_producer = None
_kafka_available = None


async def start_producer():
    """Start the Kafka producer. Called from main.py lifespan startup."""
    global _producer, _kafka_available
    try:
        from aiokafka import AIOKafkaProducer
        from config import KAFKA_BOOTSTRAP_SERVERS

        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks=1,  # leader acknowledged — good balance of durability vs latency
            compression_type="lz4",
            request_timeout_ms=5000,
        )
        await _producer.start()
        _kafka_available = True
        logger.info("kafka_producer_started")
    except Exception as e:
        _kafka_available = False
        _producer = None
        logger.warning("kafka_producer_failed", error=str(e))


async def stop_producer():
    """Stop the Kafka producer. Called from main.py lifespan shutdown."""
    global _producer, _kafka_available
    if _producer:
        try:
            await _producer.stop()
            logger.info("kafka_producer_stopped")
        except Exception:
            pass
    _producer = None
    _kafka_available = None


async def kafka_produce(topic: str, key: str, value: dict) -> bool:
    """
    Produce a message to Kafka. Returns True if sent, False if Kafka unavailable.

    The caller should fall back to synchronous DB persistence when this returns False.
    """
    if not _kafka_available or not _producer:
        return False
    try:
        await _producer.send_and_wait(topic, key=key, value=value)
        return True
    except Exception as e:
        logger.warning("kafka_produce_failed", topic=topic, error=str(e))
        return False


def create_consumer(group_id: str, topics: list[str]):
    """Factory: create a configured AIOKafkaConsumer for a consumer group."""
    from aiokafka import AIOKafkaConsumer
    from config import KAFKA_BOOTSTRAP_SERVERS

    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )


def is_kafka_available() -> bool:
    """Check if Kafka is available (for health checks)."""
    return _kafka_available is True
