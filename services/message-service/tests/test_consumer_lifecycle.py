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
