# app/consumers/persistence_consumer.py — Kafka consumer for async message persistence
#
# Architecture: The chat service (WebSocket handler) produces messages to Kafka for
# durability. This consumer reads them and persists to PostgreSQL asynchronously,
# decoupling the real-time path (WebSocket broadcast) from the storage path (Kafka -> DB).
#
# CQRS pattern: this consumer is the WRITE side. The REST API in routers/messages.py
# is the READ side. They share the same database but have different access patterns.
#
# Key difference from monolith: private messages contain sender/recipient USERNAMES,
# not user IDs. The monolith could do user_dal.get_by_username() directly against
# its local DB. In the microservice world, user data lives in the auth-service,
# so we must make an HTTP call to resolve username -> user_id.
#
# Features:
#   - Idempotent writes via message_id UUID (skip if exists)
#   - Dead Letter Queue: after 3 retries, route to chat.dlq with error context
#   - Auth Service integration with circuit breaker for username resolution
#   - Graceful shutdown via asyncio.Event
import asyncio
import time
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.infrastructure.metrics import (
    kafka_consume_duration_seconds,
    kafka_messages_consumed_total,
    messages_dlq_total,
    messages_persisted_total,
)
from app.infrastructure.auth_client import get_user_by_username
from app.infrastructure.kafka_producer import (
    TOPIC_MESSAGES,
    TOPIC_PRIVATE,
    create_consumer,
    produce_to_dlq,
)

logger = get_logger("persistence_consumer")

MAX_RETRIES = 3
# Security: limit message content size to prevent DoS from oversized Kafka messages
MAX_CONTENT_LENGTH = 10_000  # characters


class MessagePersistenceConsumer:
    """
    Consumer group 'chat-persistence' that reads from chat.messages + chat.private
    and persists each message to PostgreSQL idempotently.
    """

    def __init__(self):
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the consumer loop as a background task."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("persistence_consumer_started")

    async def stop(self):
        """Signal the consumer to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("persistence_consumer_stopped")

    async def _run(self):
        """Main consumer loop with retry on startup failures."""
        while not self._stop_event.is_set():
            consumer = None
            try:
                consumer = create_consumer(
                    group_id="chat-persistence",
                    topics=[TOPIC_MESSAGES, TOPIC_PRIVATE],
                )
                await consumer.start()
                logger.info("kafka_consumer_connected")

                async for msg in consumer:
                    if self._stop_event.is_set():
                        break
                    await self._process_with_retry(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("kafka_consumer_error", error=str(e))
                # Wait before reconnecting — but stop immediately if shutdown is signaled
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5)
                except TimeoutError:
                    pass  # retry connection
            finally:
                if consumer:
                    try:
                        await consumer.stop()
                    except Exception:
                        pass

    async def _process_with_retry(self, msg):
        """Process a single message with retry + DLQ routing."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                start = time.time()
                await self._process(msg.topic, msg.value)
                duration = time.time() - start
                kafka_consume_duration_seconds.labels(topic=msg.topic).observe(duration)
                kafka_messages_consumed_total.labels(
                    topic=msg.topic, status="success"
                ).inc()
                return
            except Exception as e:
                kafka_messages_consumed_total.labels(
                    topic=msg.topic, status="retry"
                ).inc()
                logger.warning(
                    "consumer_process_failed",
                    topic=msg.topic,
                    attempt=attempt,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * attempt)

        # All retries exhausted — route to DLQ
        await self._send_to_dlq(msg)

    async def _process(self, topic: str, value: dict):
        """
        Persist a single Kafka message to PostgreSQL.

        Uses a fresh session per message to avoid long-lived transactions.
        Idempotent: skips if message_id already exists.

        Private messages require an async HTTP call to the auth service to resolve
        usernames to user IDs, which is why this method is async (unlike the monolith).
        """
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            if topic == TOPIC_MESSAGES:
                msg_type = value.get("type", "message")
                if msg_type == "add_reaction":
                    self._persist_add_reaction(db, value)
                elif msg_type == "remove_reaction":
                    self._persist_remove_reaction(db, value)
                else:
                    self._persist_room_message(db, value)
            elif topic == TOPIC_PRIVATE:
                await self._persist_private_message(db, value)
        finally:
            db.close()

    def _persist_room_message(self, db, value: dict):
        """Persist a room chat message."""
        from app.dal import message_dal

        msg_id = value.get("msg_id")
        sender_id = value.get("sender_id")
        sender_name = value.get("username")
        room_id = value.get("room_id")
        text = value.get("text", "")
        ts_str = value.get("timestamp")

        # Security: truncate oversized message content to prevent DoS
        if len(text) > MAX_CONTENT_LENGTH:
            logger.warning(
                "message_content_truncated", msg_id=msg_id, original_length=len(text)
            )
            text = text[:MAX_CONTENT_LENGTH]

        sent_at = None
        if ts_str:
            sent_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

        inserted = message_dal.create_idempotent(
            db,
            message_id=msg_id,
            sender_id=sender_id,
            sender_name=sender_name,
            room_id=room_id,
            content=text,
            is_private=False,
            sent_at=sent_at,
        )
        if inserted:
            messages_persisted_total.labels(type="room").inc()
            logger.debug("message_persisted", msg_id=msg_id, room_id=room_id)

    async def _persist_private_message(self, db, value: dict):
        """
        Persist a private message.

        Key microservice difference: the Kafka message contains sender/recipient
        USERNAMES, not user IDs. We must call the Auth Service REST API to resolve
        them. If the auth service is unreachable, the exception bubbles up to
        _process_with_retry which will retry and eventually DLQ.
        """
        from app.dal import message_dal

        msg_id = value.get("msg_id")
        sender_name = value.get("sender")
        recipient_name = value.get("recipient")
        text = value.get("text", "")
        ts_str = value.get("timestamp")

        # Security: truncate oversized message content to prevent DoS
        if len(text) > MAX_CONTENT_LENGTH:
            logger.warning(
                "pm_content_truncated", msg_id=msg_id, original_length=len(text)
            )
            text = text[:MAX_CONTENT_LENGTH]

        sent_at = None
        if ts_str:
            sent_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

        # Resolve usernames to user IDs via Auth Service REST API
        sender = await get_user_by_username(sender_name)
        recipient = await get_user_by_username(recipient_name)

        if not sender or not recipient:
            raise ValueError(
                f"Unknown user: sender={sender_name}, recipient={recipient_name}"
            )

        sender_id = sender.get("id")
        recipient_id = recipient.get("id")

        if sender_id is None or recipient_id is None:
            raise ValueError(
                f"Auth service returned user without id: sender={sender}, recipient={recipient}"
            )

        inserted = message_dal.create_idempotent(
            db,
            message_id=msg_id,
            sender_id=sender_id,
            sender_name=sender_name,
            room_id=None,
            content=text,
            is_private=True,
            recipient_id=recipient_id,
            sent_at=sent_at,
        )
        if inserted:
            messages_persisted_total.labels(type="private").inc()
            logger.debug(
                "pm_persisted",
                msg_id=msg_id,
                sender=sender_name,
                recipient=recipient_name,
            )

    def _persist_add_reaction(self, db, value: dict):
        """Persist an add_reaction event from Kafka."""
        from app.dal import reaction_dal

        msg_id = value.get("msg_id")
        user_id = value.get("user_id")
        username = value.get("username")
        emoji = value.get("emoji")

        if any(v is None for v in [msg_id, user_id, username, emoji]):
            logger.warning("add_reaction_missing_fields", value=value)
            return

        inserted = reaction_dal.add_reaction(db, msg_id, user_id, username, emoji)
        if inserted:
            messages_persisted_total.labels(type="reaction").inc()
            logger.debug(
                "reaction_persisted", msg_id=msg_id, emoji=emoji, user=username
            )

    def _persist_remove_reaction(self, db, value: dict):
        """Persist a remove_reaction event from Kafka."""
        from app.dal import reaction_dal

        msg_id = value.get("msg_id")
        user_id = value.get("user_id")
        emoji = value.get("emoji")

        if any(v is None for v in [msg_id, user_id, emoji]):
            logger.warning("remove_reaction_missing_fields", value=value)
            return

        removed = reaction_dal.remove_reaction(db, msg_id, user_id, emoji)
        if removed:
            logger.debug("reaction_removed", msg_id=msg_id, emoji=emoji)

    async def _send_to_dlq(self, msg):
        """Route a failed message to the Dead Letter Queue with error context."""
        messages_dlq_total.inc()
        kafka_messages_consumed_total.labels(topic=msg.topic, status="dlq").inc()
        dlq_payload = {
            "original_topic": msg.topic,
            "original_key": msg.key,
            "original_value": msg.value,
            "error": "max_retries_exhausted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        produced = await produce_to_dlq(key=msg.topic, value=dlq_payload)
        if produced:
            logger.warning("message_sent_to_dlq", topic=msg.topic, key=msg.key)
        else:
            logger.error("dlq_produce_failed", topic=msg.topic, key=msg.key)
