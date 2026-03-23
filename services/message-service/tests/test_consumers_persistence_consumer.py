# tests/test_consumers_persistence_consumer.py — Tests for app/consumers/persistence_consumer.py
#
# Covers:
#   - start() creates a background task
#   - stop() signals the stop event and waits for the task
#   - stop() cancels the task on timeout
#   - _run() reconnection loop on Kafka errors
#   - _send_to_dlq when produce succeeds vs fails
#   - _persist_room_message: basic, idempotent, without timestamp
#   - _persist_private_message: success, unknown sender, auth service down, missing user id
#   - _process dispatches room and private messages correctly
#   - _process_with_retry: DLQ on persistent failure, no DLQ on success, retry then success
#   - Content truncation (DoS prevention)
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.consumers.persistence_consumer import MAX_CONTENT_LENGTH, MessagePersistenceConsumer
from app.infrastructure.kafka_producer import TOPIC_MESSAGES, TOPIC_PRIVATE
from app.models import Message


# ══════════════════════════════════════════════════════════════════════
# Consumer lifecycle: start / stop
# ══════════════════════════════════════════════════════════════════════


class TestConsumerLifecycle:
    """Tests for consumer start() and stop() methods."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """start() should create a background task and clear the stop event."""
        consumer = MessagePersistenceConsumer()

        with patch.object(consumer, "_run", new_callable=AsyncMock) as mock_run:
            await consumer.start()

            assert consumer._task is not None
            assert not consumer._stop_event.is_set()

            # Clean up
            consumer._stop_event.set()
            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_signals_and_waits(self):
        """stop() should set the stop event and wait for the task to finish."""
        consumer = MessagePersistenceConsumer()

        async def mock_run():
            await consumer._stop_event.wait()

        consumer._stop_event.clear()
        consumer._task = asyncio.create_task(mock_run())

        await consumer.stop()

        assert consumer._stop_event.is_set()
        assert consumer._task.done()

    @pytest.mark.asyncio
    async def test_stop_cancels_on_timeout(self):
        """stop() should cancel the task if it doesn't finish within timeout."""
        consumer = MessagePersistenceConsumer()

        async def mock_run_forever():
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                raise

        consumer._stop_event.clear()
        consumer._task = asyncio.create_task(mock_run_forever())

        # Patch wait_for to immediately raise TimeoutError (simulating timeout)
        with patch(
            "app.consumers.persistence_consumer.asyncio.wait_for",
            side_effect=TimeoutError(),
        ):
            await consumer.stop()

        assert consumer._stop_event.is_set()
        await asyncio.sleep(0.05)  # Let cancel propagate

    @pytest.mark.asyncio
    async def test_stop_with_no_task(self):
        """stop() should handle None task gracefully."""
        consumer = MessagePersistenceConsumer()
        consumer._task = None

        await consumer.stop()  # Should not raise
        assert consumer._stop_event.is_set()


# ══════════════════════════════════════════════════════════════════════
# Consumer _run loop
# ══════════════════════════════════════════════════════════════════════


class TestConsumerRunLoop:
    """Tests for the consumer's main _run loop and reconnection logic."""

    @pytest.mark.asyncio
    async def test_run_breaks_on_cancelled_error(self):
        """_run() should exit cleanly on CancelledError."""
        consumer = MessagePersistenceConsumer()

        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start.side_effect = asyncio.CancelledError()

        with patch(
            "app.consumers.persistence_consumer.create_consumer",
            return_value=mock_consumer_instance,
        ):
            consumer._stop_event.clear()
            await consumer._run()
            # Should complete without hanging

    @pytest.mark.asyncio
    async def test_run_reconnects_on_error(self):
        """_run() should attempt to reconnect after an error."""
        consumer = MessagePersistenceConsumer()
        attempt_count = 0

        def mock_create_consumer(group_id, topics):
            nonlocal attempt_count
            attempt_count += 1
            mock_c = AsyncMock()
            mock_c.start.side_effect = Exception("broker unavailable")
            return mock_c

        with patch(
            "app.consumers.persistence_consumer.create_consumer",
            side_effect=mock_create_consumer,
        ):
            consumer._stop_event.clear()
            task = asyncio.create_task(consumer._run())

            # Let it attempt a few reconnections
            await asyncio.sleep(0.2)

            # Signal stop
            consumer._stop_event.set()
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        assert attempt_count >= 1

    @pytest.mark.asyncio
    async def test_run_consumer_stop_called_in_finally(self):
        """_run() should always call consumer.stop() in the finally block."""
        consumer_obj = MessagePersistenceConsumer()

        mock_kafka_consumer = AsyncMock()
        mock_kafka_consumer.start.return_value = None

        # Make the async iterator raise to trigger the except/finally block
        async def raise_on_iter():
            raise Exception("processing error")
            yield  # noqa: unreachable - needed to make this an async generator

        mock_kafka_consumer.__aiter__ = lambda self: raise_on_iter()

        call_count = 0

        def create_and_count(group_id, topics):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                consumer_obj._stop_event.set()
            return mock_kafka_consumer

        with patch(
            "app.consumers.persistence_consumer.create_consumer",
            side_effect=create_and_count,
        ):
            consumer_obj._stop_event.clear()
            task = asyncio.create_task(consumer_obj._run())

            # Wait for the loop to process
            await asyncio.sleep(0.3)
            consumer_obj._stop_event.set()

            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # consumer.stop should have been called at least once in finally
        mock_kafka_consumer.stop.assert_called()

    @pytest.mark.asyncio
    async def test_run_processes_messages(self):
        """_run() should process each message from the consumer."""
        consumer_obj = MessagePersistenceConsumer()

        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_MESSAGES
        mock_msg.value = {"msg_id": "test", "text": "hello"}

        mock_kafka_consumer = AsyncMock()
        mock_kafka_consumer.start.return_value = None

        messages_yielded = False

        async def fake_iter():
            nonlocal messages_yielded
            yield mock_msg
            messages_yielded = True
            consumer_obj._stop_event.set()

        mock_kafka_consumer.__aiter__ = lambda self: fake_iter()

        with patch(
            "app.consumers.persistence_consumer.create_consumer",
            return_value=mock_kafka_consumer,
        ):
            with patch.object(
                consumer_obj, "_process_with_retry", new_callable=AsyncMock
            ) as mock_process:
                consumer_obj._stop_event.clear()
                task = asyncio.create_task(consumer_obj._run())

                await asyncio.sleep(0.2)
                consumer_obj._stop_event.set()

                try:
                    await asyncio.wait_for(task, timeout=5)
                except asyncio.TimeoutError:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                mock_process.assert_called_once_with(mock_msg)


# ══════════════════════════════════════════════════════════════════════
# _send_to_dlq
# ══════════════════════════════════════════════════════════════════════


class TestSendToDlq:
    """Tests for the DLQ routing method."""

    @pytest.mark.asyncio
    async def test_send_to_dlq_success(self):
        """Should call produce_to_dlq with correct payload."""
        consumer = MessagePersistenceConsumer()
        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_MESSAGES
        mock_msg.key = "test-key"
        mock_msg.value = {"msg_id": "fail-1", "text": "failed"}

        with patch(
            "app.consumers.persistence_consumer.produce_to_dlq",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_dlq:
            await consumer._send_to_dlq(mock_msg)

            mock_dlq.assert_called_once()
            payload = mock_dlq.call_args.kwargs["value"]
            assert payload["original_topic"] == TOPIC_MESSAGES
            assert payload["original_key"] == "test-key"
            assert payload["error"] == "max_retries_exhausted"
            assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_send_to_dlq_failure_logged(self):
        """When produce_to_dlq returns False, should log the failure."""
        consumer = MessagePersistenceConsumer()
        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_PRIVATE
        mock_msg.key = "pm-key"
        mock_msg.value = {"msg_id": "fail-2"}

        with patch(
            "app.consumers.persistence_consumer.produce_to_dlq",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_dlq:
            # Should not raise even though DLQ write failed
            await consumer._send_to_dlq(mock_msg)
            mock_dlq.assert_called_once()


# ══════════════════════════════════════════════════════════════════════
# Room message persistence
# ══════════════════════════════════════════════════════════════════════


class TestPersistRoomMessage:
    """Tests for the consumer's room message persistence (_persist_room_message)."""

    def test_persist_room_message(self, db, consumer):
        """Consumer should persist a room message to the DB."""
        ts = datetime.now(timezone.utc).isoformat()
        consumer._persist_room_message(
            db,
            {
                "msg_id": "test-uuid-001",
                "sender_id": 42,
                "room_id": 1,
                "text": "Hello from Kafka!",
                "timestamp": ts,
            },
        )

        msg = db.query(Message).filter(Message.message_id == "test-uuid-001").first()
        assert msg is not None
        assert msg.content == "Hello from Kafka!"
        assert msg.sender_id == 42
        assert msg.room_id == 1
        assert msg.is_private is False

    def test_idempotent_room_message(self, db, consumer):
        """Duplicate msg_id should NOT create a second row."""
        value = {
            "msg_id": "test-uuid-dup",
            "sender_id": 42,
            "room_id": 1,
            "text": "first write",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        consumer._persist_room_message(db, value)
        consumer._persist_room_message(db, value)  # duplicate

        count = db.query(Message).filter(Message.message_id == "test-uuid-dup").count()
        assert count == 1

    def test_persist_message_without_timestamp(self, db, consumer):
        """Consumer should handle messages without a timestamp (uses DB default)."""
        consumer._persist_room_message(
            db,
            {
                "msg_id": "test-uuid-no-ts",
                "sender_id": 42,
                "room_id": 1,
                "text": "No timestamp",
            },
        )

        msg = db.query(Message).filter(Message.message_id == "test-uuid-no-ts").first()
        assert msg is not None
        assert msg.sent_at is not None  # DB default should kick in

    def test_process_dispatches_room_message(self, db, consumer, monkeypatch):
        """_process() should route TOPIC_MESSAGES to _persist_room_message."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        asyncio.get_event_loop().run_until_complete(
            consumer._process(
                TOPIC_MESSAGES,
                {
                    "msg_id": "dispatch-test",
                    "sender_id": 42,
                    "room_id": 1,
                    "text": "Dispatched!",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        )

        msg = db.query(Message).filter(Message.message_id == "dispatch-test").first()
        assert msg is not None
        assert msg.content == "Dispatched!"


# ══════════════════════════════════════════════════════════════════════
# Private message persistence
# ══════════════════════════════════════════════════════════════════════


class TestPersistPrivateMessage:
    """Tests for the consumer's private message persistence (_persist_private_message)."""

    @pytest.mark.asyncio
    async def test_persist_private_message(self, db, consumer):
        """Consumer should persist a PM after resolving usernames via Auth Service."""
        mock_sender = {"id": 10, "username": "alice"}
        mock_recipient = {"id": 20, "username": "bob"}

        with patch("app.consumers.persistence_consumer.get_user_by_username") as mock_get_user:
            mock_get_user.side_effect = lambda name: {
                "alice": mock_sender,
                "bob": mock_recipient,
            }.get(name)

            await consumer._persist_private_message(
                db,
                {
                    "msg_id": "pm-uuid-001",
                    "sender": "alice",
                    "recipient": "bob",
                    "text": "Secret PM",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        msg = db.query(Message).filter(Message.message_id == "pm-uuid-001").first()
        assert msg is not None
        assert msg.content == "Secret PM"
        assert msg.is_private is True
        assert msg.sender_id == 10
        assert msg.recipient_id == 20
        assert msg.room_id is None

    @pytest.mark.asyncio
    async def test_private_message_unknown_sender_raises(self, db, consumer):
        """Consumer should raise if the sender username doesn't resolve."""
        with patch("app.consumers.persistence_consumer.get_user_by_username") as mock_get_user:
            mock_get_user.return_value = None  # user not found

            with pytest.raises(ValueError, match="Unknown user"):
                await consumer._persist_private_message(
                    db,
                    {
                        "msg_id": "pm-uuid-bad",
                        "sender": "nonexistent",
                        "recipient": "bob",
                        "text": "Should fail",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

    @pytest.mark.asyncio
    async def test_private_message_auth_service_down_raises(self, db, consumer):
        """Consumer should raise ConnectionError if Auth Service is unreachable."""
        with patch("app.consumers.persistence_consumer.get_user_by_username") as mock_get_user:
            mock_get_user.side_effect = ConnectionError("Auth service unreachable")

            with pytest.raises(ConnectionError):
                await consumer._persist_private_message(
                    db,
                    {
                        "msg_id": "pm-uuid-down",
                        "sender": "alice",
                        "recipient": "bob",
                        "text": "Auth down",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

    @pytest.mark.asyncio
    async def test_persist_private_message_user_without_id(self, db):
        """Should raise ValueError when auth service returns a user without 'id' field."""
        consumer = MessagePersistenceConsumer()

        mock_sender = {"username": "alice"}  # Missing 'id'
        mock_recipient = {"id": 20, "username": "bob"}

        with patch(
            "app.consumers.persistence_consumer.get_user_by_username"
        ) as mock_get_user:
            mock_get_user.side_effect = lambda name: {
                "alice": mock_sender,
                "bob": mock_recipient,
            }.get(name)

            with pytest.raises(ValueError, match="without id"):
                await consumer._persist_private_message(
                    db,
                    {
                        "msg_id": "pm-no-id",
                        "sender": "alice",
                        "recipient": "bob",
                        "text": "Missing sender id",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

    @pytest.mark.asyncio
    async def test_process_dispatches_private_message(self, db, consumer, monkeypatch):
        """_process() should route TOPIC_PRIVATE to _persist_private_message."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        mock_sender = {"id": 10, "username": "alice"}
        mock_recipient = {"id": 20, "username": "bob"}

        with patch("app.consumers.persistence_consumer.get_user_by_username") as mock_get_user:
            mock_get_user.side_effect = lambda name: {
                "alice": mock_sender,
                "bob": mock_recipient,
            }.get(name)

            await consumer._process(
                TOPIC_PRIVATE,
                {
                    "msg_id": "dispatch-pm-test",
                    "sender": "alice",
                    "recipient": "bob",
                    "text": "PM dispatched!",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        msg = db.query(Message).filter(Message.message_id == "dispatch-pm-test").first()
        assert msg is not None
        assert msg.content == "PM dispatched!"
        assert msg.is_private is True


# ══════════════════════════════════════════════════════════════════════
# DLQ routing via _process_with_retry
# ══════════════════════════════════════════════════════════════════════


class TestProcessWithRetryDLQ:
    """Tests for the consumer's _process_with_retry and DLQ routing."""

    @pytest.mark.asyncio
    async def test_dlq_on_persistent_failure(self, consumer):
        """After MAX_RETRIES failures, message should be routed to DLQ."""
        # Create a mock Kafka message
        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_MESSAGES
        mock_msg.key = "test-key"
        mock_msg.value = {"msg_id": "fail-msg", "text": "will fail"}

        with (
            patch.object(consumer, "_process", new_callable=AsyncMock) as mock_process,
            patch("app.consumers.persistence_consumer.produce_to_dlq", new_callable=AsyncMock) as mock_dlq,
        ):
            mock_process.side_effect = Exception("DB error")
            mock_dlq.return_value = True

            await consumer._process_with_retry(mock_msg)

            # Should have been called MAX_RETRIES times
            assert mock_process.call_count == 3
            # Should have sent to DLQ
            mock_dlq.assert_called_once()
            dlq_call_args = mock_dlq.call_args
            assert dlq_call_args.kwargs["key"] == TOPIC_MESSAGES
            dlq_value = dlq_call_args.kwargs["value"]
            assert dlq_value["original_topic"] == TOPIC_MESSAGES
            assert dlq_value["error"] == "max_retries_exhausted"

    @pytest.mark.asyncio
    async def test_no_dlq_on_success(self, consumer):
        """Successful processing should NOT trigger DLQ."""
        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_MESSAGES
        mock_msg.value = {"msg_id": "ok-msg", "text": "success"}

        with (
            patch.object(consumer, "_process", new_callable=AsyncMock) as mock_process,
            patch("app.consumers.persistence_consumer.produce_to_dlq", new_callable=AsyncMock) as mock_dlq,
        ):
            await consumer._process_with_retry(mock_msg)

            mock_process.assert_called_once()
            mock_dlq.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_then_success(self, consumer):
        """If processing succeeds after a retry, should NOT go to DLQ."""
        mock_msg = MagicMock()
        mock_msg.topic = TOPIC_MESSAGES
        mock_msg.value = {"msg_id": "retry-msg", "text": "retry"}

        call_count = 0

        async def flaky_process(topic, value):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient error")

        with (
            patch.object(consumer, "_process", side_effect=flaky_process) as mock_process,
            patch("app.consumers.persistence_consumer.produce_to_dlq", new_callable=AsyncMock) as mock_dlq,
        ):
            await consumer._process_with_retry(mock_msg)

            assert call_count == 2  # Failed once, succeeded on retry
            mock_dlq.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
# Content length validation (DoS prevention)
# ══════════════════════════════════════════════════════════════════════


class TestContentTruncation:
    """Tests for content length limits on Kafka messages."""

    def test_oversized_room_message_is_truncated(self, db, consumer):
        """Room messages exceeding MAX_CONTENT_LENGTH should be truncated."""
        oversized_text = "x" * (MAX_CONTENT_LENGTH + 5000)
        consumer._persist_room_message(
            db,
            {
                "msg_id": "oversized-msg",
                "sender_id": 1,
                "room_id": 1,
                "text": oversized_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        msg = db.query(Message).filter(Message.message_id == "oversized-msg").first()
        assert msg is not None
        assert len(msg.content) == MAX_CONTENT_LENGTH

    def test_normal_message_not_truncated(self, db, consumer):
        """Messages within MAX_CONTENT_LENGTH should not be truncated."""
        normal_text = "Hello, world!"
        consumer._persist_room_message(
            db,
            {
                "msg_id": "normal-msg",
                "sender_id": 1,
                "room_id": 1,
                "text": normal_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        msg = db.query(Message).filter(Message.message_id == "normal-msg").first()
        assert msg is not None
        assert msg.content == normal_text
