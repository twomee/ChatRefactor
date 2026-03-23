# infrastructure/kafka/consumers.py — Kafka consumer for async message persistence
#
# Architecture: The WebSocket handler produces messages to Kafka for durability.
# This consumer reads them and persists to PostgreSQL asynchronously, decoupling
# the real-time path (Redis pub/sub → WebSocket) from the storage path (Kafka → DB).
#
# Features:
#   - Idempotent writes via message_id UUID (ON CONFLICT skip)
#   - Dead Letter Queue: after 3 retries, route to chat.dlq with error context
#   - Graceful shutdown via asyncio.Event

import asyncio
from datetime import datetime, timezone

from core.logging import get_logger
from infrastructure.kafka.producer import create_consumer, kafka_produce
from infrastructure.kafka.topics import TOPIC_DLQ, TOPIC_MESSAGES, TOPIC_PRIVATE

logger = get_logger("kafka_consumers")

MAX_RETRIES = 3


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
                # Wait before reconnecting
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5)
                except TimeoutError:
                    pass  # retry
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
                self._process(msg.topic, msg.value)
                return
            except Exception as e:
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

    def _process(self, topic: str, value: dict):
        """
        Persist a single Kafka message to PostgreSQL.

        Uses a fresh session per message to avoid long-lived transactions.
        Idempotent: skips if message_id already exists.
        """
        from core.database import SessionLocal

        db = SessionLocal()
        try:
            if topic == TOPIC_MESSAGES:
                self._persist_room_message(db, value)
            elif topic == TOPIC_PRIVATE:
                self._persist_private_message(db, value)
        finally:
            db.close()

    def _persist_room_message(self, db, value: dict):
        """Persist a room chat message."""
        from dal import message_dal

        msg_id = value.get("msg_id")
        sender_id = value.get("sender_id")
        room_id = value.get("room_id")
        text = value.get("text", "")
        ts_str = value.get("timestamp")

        sent_at = None
        if ts_str:
            sent_at = datetime.fromisoformat(ts_str)

        inserted = message_dal.create_idempotent(
            db,
            message_id=msg_id,
            sender_id=sender_id,
            room_id=room_id,
            content=text,
            is_private=False,
            sent_at=sent_at,
        )
        if inserted:
            logger.debug("message_persisted", msg_id=msg_id, room_id=room_id)

    def _persist_private_message(self, db, value: dict):
        """Persist a private message."""
        from dal import message_dal, user_dal

        msg_id = value.get("msg_id")
        sender_name = value.get("sender")
        recipient_name = value.get("recipient")
        text = value.get("text", "")
        ts_str = value.get("timestamp")

        sent_at = None
        if ts_str:
            sent_at = datetime.fromisoformat(ts_str)

        # Look up user IDs by username
        sender = user_dal.get_by_username(db, sender_name)
        recipient = user_dal.get_by_username(db, recipient_name)
        if not sender or not recipient:
            raise ValueError(f"Unknown user: sender={sender_name}, recipient={recipient_name}")

        inserted = message_dal.create_idempotent(
            db,
            message_id=msg_id,
            sender_id=sender.id,
            room_id=None,
            content=text,
            is_private=True,
            recipient_id=recipient.id,
            sent_at=sent_at,
        )
        if inserted:
            logger.debug("pm_persisted", msg_id=msg_id, sender=sender_name, recipient=recipient_name)

    async def _send_to_dlq(self, msg):
        """Route a failed message to the Dead Letter Queue with error context."""
        dlq_payload = {
            "original_topic": msg.topic,
            "original_key": msg.key,
            "original_value": msg.value,
            "error": "max_retries_exhausted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        produced = await kafka_produce(TOPIC_DLQ, key=msg.topic, value=dlq_payload)
        if produced:
            logger.warning("message_sent_to_dlq", topic=msg.topic, key=msg.key)
        else:
            logger.error("dlq_produce_failed", topic=msg.topic, key=msg.key)
