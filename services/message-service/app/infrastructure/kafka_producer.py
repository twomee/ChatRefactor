# app/infrastructure/kafka_producer.py — Kafka producer for DLQ only
#
# The message service consumes from Kafka (chat.messages, chat.private) and persists
# to PostgreSQL. The only topic it produces to is chat.dlq — for messages that fail
# after all retry attempts.
#
# Graceful degradation: if Kafka is unavailable, the DLQ write is logged but the
# consumer continues processing. A failed DLQ write is not a reason to crash.
import json

from app.core.logging import get_logger

logger = get_logger("kafka_producer")

_producer = None
_kafka_available = None

TOPIC_DLQ = "chat.dlq"
TOPIC_MESSAGES = "chat.messages"
TOPIC_PRIVATE = "chat.private"


async def init_producer():
    """Start the Kafka producer. Called from main.py lifespan startup."""
    global _producer, _kafka_available
    try:
        from aiokafka import AIOKafkaProducer

        from app.core.config import KAFKA_BOOTSTRAP_SERVERS

        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks=1,
            request_timeout_ms=5000,
        )
        await _producer.start()
        _kafka_available = True
        logger.info("kafka_producer_started")
    except Exception as e:
        _kafka_available = False
        _producer = None
        logger.warning("kafka_producer_start_failed", error=str(e))


async def close_producer():
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


async def produce_to_dlq(key: str, value: dict) -> bool:
    """
    Produce a message to the Dead Letter Queue. Returns True if sent, False otherwise.

    Fire-and-forget: the caller should NOT fail if this returns False.
    Failed DLQ writes are logged but do not block the consumer.
    """
    if not _kafka_available or not _producer:
        logger.warning("kafka_unavailable", action="dlq_produce")
        return False
    try:
        await _producer.send_and_wait(TOPIC_DLQ, key=key, value=value)
        logger.warning("message_sent_to_dlq", key=key)
        return True
    except Exception as e:
        logger.error("dlq_produce_failed", key=key, error=str(e))
        return False


def create_consumer(group_id: str, topics: list[str]):
    """Factory: create a configured AIOKafkaConsumer for a consumer group."""
    from aiokafka import AIOKafkaConsumer

    from app.core.config import KAFKA_BOOTSTRAP_SERVERS

    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        auto_offset_reset="earliest",
        # Manual commit: offsets are committed only after successful DB write.
        # This guarantees at-least-once delivery — if the process crashes mid-write,
        # the message is re-consumed on restart rather than silently lost.
        enable_auto_commit=False,
    )


def is_kafka_available() -> bool:
    """Check if Kafka producer is connected (for health checks)."""
    return _kafka_available is True
