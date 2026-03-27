# app/infrastructure/kafka_producer.py — Async Kafka producer with graceful degradation
"""
Produces events to the auth.events topic. Fire-and-forget semantics: if Kafka is
unavailable, the auth operation still succeeds but the event is lost. This is acceptable
because auth events are used for notifications/analytics, not for critical data flow.

Event types:
- user_registered: { user_id, username }
- user_logged_in:  { user_id, username }
- user_logged_out: { user_id, username }
"""

import json
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.infrastructure.metrics import kafka_events_produced_total

logger = get_logger("kafka_producer")

# Module-level singleton — lazy-initialized
_producer = None
_kafka_available = None

AUTH_EVENTS_TOPIC = "auth.events"


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
            compression_type="lz4",
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


async def produce_event(event_type: str, data: dict) -> bool:
    """Produce an auth event to Kafka. Returns True if sent, False otherwise.

    Fire-and-forget: the caller should NOT fail if this returns False.
    Auth operations must succeed even when Kafka is down.
    """
    if not _kafka_available or not _producer:
        logger.debug("kafka_unavailable", event_type=event_type)
        return False
    try:
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        key = data.get("username", str(data.get("user_id", "")))
        await _producer.send_and_wait(AUTH_EVENTS_TOPIC, key=key, value=event)
        kafka_events_produced_total.labels(topic="auth.events", status="success").inc()
        logger.info("auth_event_produced", event_type=event_type, key=key)
        return True
    except Exception as e:
        kafka_events_produced_total.labels(topic="auth.events", status="failed").inc()
        logger.warning("kafka_produce_failed", event_type=event_type, error=str(e))
        return False


def is_kafka_available() -> bool:
    """Check if Kafka producer is connected (for health checks)."""
    return _kafka_available is True
