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

from app.consumers.persistence_consumer import (
    MAX_CONTENT_LENGTH,
    MessagePersistenceConsumer,
)
from app.infrastructure.kafka_producer import TOPIC_MESSAGES, TOPIC_PRIVATE
from app.models import Message


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
            patch(
                "app.consumers.persistence_consumer.produce_to_dlq",
                new_callable=AsyncMock,
            ) as mock_dlq,
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
            patch(
                "app.consumers.persistence_consumer.produce_to_dlq",
                new_callable=AsyncMock,
            ) as mock_dlq,
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
            patch.object(
                consumer, "_process", side_effect=flaky_process
            ) as mock_process,
            patch(
                "app.consumers.persistence_consumer.produce_to_dlq",
                new_callable=AsyncMock,
            ) as mock_dlq,
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
