# tests/test_infrastructure_kafka_producer.py — Unit tests for app/infrastructure/kafka_producer.py
"""
Tests for init_producer, close_producer, produce_event, and is_kafka_available.
Uses mocking to avoid requiring a real Kafka cluster.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure import kafka_producer

# Save a reference to the REAL produce_event before conftest's autouse fixture
# patches it. This lets us test the actual implementation.
_real_produce_event = kafka_producer.produce_event


@pytest.fixture(autouse=True)
def reset_producer_state():
    """Reset module-level producer state before and after each test."""
    orig_producer = kafka_producer._producer
    orig_available = kafka_producer._kafka_available
    kafka_producer._producer = None
    kafka_producer._kafka_available = None
    yield
    kafka_producer._producer = orig_producer
    kafka_producer._kafka_available = orig_available


# -- is_kafka_available --------------------------------------------------------


class TestIsKafkaAvailable:
    """Tests for is_kafka_available()."""

    def test_returns_false_when_not_initialized(self):
        assert kafka_producer.is_kafka_available() is False

    def test_returns_true_when_available(self):
        kafka_producer._kafka_available = True
        assert kafka_producer.is_kafka_available() is True

    def test_returns_false_when_explicitly_unavailable(self):
        kafka_producer._kafka_available = False
        assert kafka_producer.is_kafka_available() is False


# -- init_producer -------------------------------------------------------------


class TestInitProducer:
    """Tests for init_producer()."""

    @pytest.mark.asyncio
    async def test_init_producer_success(self):
        mock_producer_instance = AsyncMock()
        mock_producer_instance.start = AsyncMock()
        mock_producer_cls = MagicMock(return_value=mock_producer_instance)
        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer = mock_producer_cls

        with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
            await kafka_producer.init_producer()

        assert kafka_producer._kafka_available is True
        assert kafka_producer._producer is mock_producer_instance
        mock_producer_instance.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_init_producer_failure_degrades_gracefully(self):
        """When Kafka connection fails, producer should be None and kafka_available False."""
        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer = MagicMock(
            side_effect=Exception("Connection refused")
        )

        with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
            await kafka_producer.init_producer()

        assert kafka_producer._kafka_available is False
        assert kafka_producer._producer is None


# -- close_producer ------------------------------------------------------------


class TestCloseProducer:
    """Tests for close_producer()."""

    @pytest.mark.asyncio
    async def test_close_producer_when_running(self):
        mock_producer = AsyncMock()
        mock_producer.stop = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await kafka_producer.close_producer()

        mock_producer.stop.assert_awaited_once()
        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None

    @pytest.mark.asyncio
    async def test_close_producer_when_not_running(self):
        """Closing when no producer is set should not raise."""
        kafka_producer._producer = None
        kafka_producer._kafka_available = None

        await kafka_producer.close_producer()

        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None

    @pytest.mark.asyncio
    async def test_close_producer_handles_stop_exception(self):
        """If stop() raises, close_producer should still reset state."""
        mock_producer = AsyncMock()
        mock_producer.stop = AsyncMock(side_effect=Exception("stop failed"))
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await kafka_producer.close_producer()

        assert kafka_producer._producer is None
        assert kafka_producer._kafka_available is None


# -- produce_event -------------------------------------------------------------


class TestProduceEvent:
    """Tests for produce_event().

    Uses _real_produce_event to bypass conftest's autouse mock of produce_event.
    """

    @pytest.mark.asyncio
    async def test_produce_event_returns_false_when_unavailable(self):
        kafka_producer._kafka_available = False
        kafka_producer._producer = None

        result = await _real_produce_event(
            "user_logged_in", {"user_id": 1, "username": "bob"}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_produce_event_success(self):
        mock_producer = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        result = await _real_produce_event(
            "user_registered", {"user_id": 1, "username": "alice"}
        )

        assert result is True
        mock_producer.send.assert_awaited_once()
        call_args = mock_producer.send.call_args
        assert call_args.args[0] == "auth.events"  # topic
        assert call_args.kwargs["key"] == "alice"

    @pytest.mark.asyncio
    async def test_produce_event_returns_false_on_send_failure(self):
        mock_producer = AsyncMock()
        mock_producer.send.side_effect = Exception("broker down")
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        result = await _real_produce_event(
            "user_logged_out", {"user_id": 1, "username": "carol"}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_produce_event_uses_user_id_as_key_when_no_username(self):
        mock_producer = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await _real_produce_event("user_registered", {"user_id": 42})

        call_args = mock_producer.send.call_args
        assert call_args.kwargs["key"] == "42"

    @pytest.mark.asyncio
    async def test_produce_event_includes_event_type_and_timestamp(self):
        mock_producer = AsyncMock()
        kafka_producer._producer = mock_producer
        kafka_producer._kafka_available = True

        await _real_produce_event("user_registered", {"user_id": 1, "username": "dave"})

        call_args = mock_producer.send.call_args
        event_value = call_args.kwargs["value"]
        assert event_value["event_type"] == "user_registered"
        assert "timestamp" in event_value
        assert event_value["user_id"] == 1
        assert event_value["username"] == "dave"
