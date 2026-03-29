# tests/test_infrastructure_kafka_producer.py — Tests for app/infrastructure/kafka_producer.py
#
# Covers:
#   - init_producer: success, failure (Kafka unavailable)
#   - close_producer: with running producer, with no producer, stop exception
#   - produce_to_dlq: success, failure, Kafka unavailable
#   - create_consumer: factory returns configured consumer
#   - is_kafka_available: reflects producer state
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure import kafka_producer
from app.infrastructure.kafka_producer import (
    TOPIC_DLQ,
    close_producer,
    create_consumer,
    init_producer,
    is_kafka_available,
    produce_to_dlq,
)


@pytest.fixture(autouse=True)
def _reset_producer_state():
    """Reset module-level producer state before and after each test."""
    kafka_producer._producer = None
    kafka_producer._kafka_available = None
    yield
    kafka_producer._producer = None
    kafka_producer._kafka_available = None


# ══════════════════════════════════════════════════════════════════════
# init_producer
# ══════════════════════════════════════════════════════════════════════


class TestInitProducer:
    """Tests for Kafka producer initialization."""

    @pytest.mark.asyncio
    async def test_init_producer_success(self):
        """Should start producer and set _kafka_available to True."""
        mock_producer_instance = AsyncMock()

        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer.return_value = mock_producer_instance

        with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
            await init_producer()

        assert kafka_producer._kafka_available is True
        assert kafka_producer._producer is mock_producer_instance
        mock_producer_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_producer_failure(self):
        """Should set _kafka_available to False when Kafka is unreachable."""
        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer.side_effect = Exception("connection refused")

        with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
            await init_producer()

        assert kafka_producer._kafka_available is False
        assert kafka_producer._producer is None


# ══════════════════════════════════════════════════════════════════════
# close_producer
# ══════════════════════════════════════════════════════════════════════


class TestCloseProducer:
    """Tests for Kafka producer shutdown."""

    @pytest.mark.asyncio
    async def test_close_producer_with_running_producer(self):
        """Should stop the producer and reset state."""
        mock_producer = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await close_producer()

        mock_producer.stop.assert_called_once()
        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None

    @pytest.mark.asyncio
    async def test_close_producer_no_producer(self):
        """Should handle None producer gracefully."""
        kafka_producer._producer = None
        kafka_producer._kafka_available = None

        await close_producer()  # Should not raise

        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None

    @pytest.mark.asyncio
    async def test_close_producer_stop_raises(self):
        """Should swallow exceptions from producer.stop() and still reset state."""
        mock_producer = AsyncMock()
        mock_producer.stop.side_effect = Exception("stop failed")
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await close_producer()  # Should not raise

        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None


# ══════════════════════════════════════════════════════════════════════
# produce_to_dlq
# ══════════════════════════════════════════════════════════════════════


class TestProduceToDlq:
    """Tests for DLQ message production."""

    @pytest.mark.asyncio
    async def test_produce_to_dlq_success(self):
        """Should send message to DLQ topic and return True."""
        mock_producer = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        result = await produce_to_dlq(key="test-key", value={"error": "failed"})

        assert result is True
        mock_producer.send_and_wait.assert_called_once_with(
            TOPIC_DLQ, key="test-key", value={"error": "failed"}
        )

    @pytest.mark.asyncio
    async def test_produce_to_dlq_kafka_unavailable(self):
        """Should return False when Kafka is unavailable."""
        kafka_producer._kafka_available = False
        kafka_producer._producer = None

        result = await produce_to_dlq(key="test-key", value={"error": "failed"})

        assert result is False

    @pytest.mark.asyncio
    async def test_produce_to_dlq_no_producer(self):
        """Should return False when producer is None even if kafka_available is True."""
        kafka_producer._kafka_available = True
        kafka_producer._producer = None

        result = await produce_to_dlq(key="test-key", value={"error": "failed"})

        assert result is False

    @pytest.mark.asyncio
    async def test_produce_to_dlq_send_fails(self):
        """Should return False and log error when send_and_wait raises."""
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = Exception("broker unavailable")
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        result = await produce_to_dlq(key="test-key", value={"error": "failed"})

        assert result is False


# ══════════════════════════════════════════════════════════════════════
# create_consumer
# ══════════════════════════════════════════════════════════════════════


class TestCreateConsumer:
    """Tests for the consumer factory function."""

    def test_create_consumer_returns_consumer(self):
        """Should create an AIOKafkaConsumer with correct configuration."""
        mock_consumer_instance = MagicMock()
        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaConsumer.return_value = mock_consumer_instance

        with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
            result = create_consumer(group_id="test-group", topics=["topic1", "topic2"])

        assert result is mock_consumer_instance
        mock_aiokafka.AIOKafkaConsumer.assert_called_once()
        call_args = mock_aiokafka.AIOKafkaConsumer.call_args
        assert "topic1" in call_args.args
        assert "topic2" in call_args.args
        assert call_args.kwargs["group_id"] == "test-group"
        assert call_args.kwargs["auto_offset_reset"] == "earliest"
        assert call_args.kwargs["enable_auto_commit"] is True


# ══════════════════════════════════════════════════════════════════════
# is_kafka_available
# ══════════════════════════════════════════════════════════════════════


class TestIsKafkaAvailable:
    """Tests for the Kafka availability check."""

    def test_returns_true_when_available(self):
        """Should return True when producer is connected."""
        kafka_producer._kafka_available = True
        assert is_kafka_available() is True

    def test_returns_false_when_unavailable(self):
        """Should return False when producer failed to start."""
        kafka_producer._kafka_available = False
        assert is_kafka_available() is False

    def test_returns_false_when_none(self):
        """Should return False when producer has not been initialized."""
        kafka_producer._kafka_available = None
        assert is_kafka_available() is False
