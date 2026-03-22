# tests/test_messages.py — Comprehensive tests for the message service
#
# Covers:
#   - GET /messages/rooms/{id}?since=...&limit=... (replay endpoint)
#   - GET /messages/rooms/{id}/history (history endpoint)
#   - Kafka consumer: persist room message, persist PM, idempotent duplicate skip, DLQ on failure
#   - Health endpoints (/health, /ready)
#   - Auth: valid token, invalid token, expired token, missing token
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.infrastructure.kafka_producer import TOPIC_MESSAGES, TOPIC_PRIVATE
from app.models import Message


# ══════════════════════════════════════════════════════════════════════
# REST API — Replay endpoint: GET /messages/rooms/{room_id}?since=...
# ══════════════════════════════════════════════════════════════════════


class TestReplayEndpoint:
    """Tests for GET /messages/rooms/{room_id}?since=...&limit=..."""

    def test_replay_returns_messages_since_timestamp(self, client, auth_headers, sample_messages):
        """Should return messages after the given timestamp."""
        since = "2025-01-01T12:02:00"
        response = client.get(f"/messages/rooms/1?since={since}&limit=100", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # Messages at 12:02, 12:03, 12:04 should be returned (3 messages)
        assert len(data) == 3
        assert data[0]["content"] == "Test message 2"
        assert data[-1]["content"] == "Test message 4"

    def test_replay_returns_empty_list_when_no_messages(self, client, auth_headers):
        """Should return empty list for a room with no messages."""
        since = "2025-01-01T00:00:00"
        response = client.get(f"/messages/rooms/999?since={since}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_replay_returns_empty_when_since_is_after_all_messages(self, client, auth_headers, sample_messages):
        """Should return empty list when 'since' is after all messages."""
        since = "2026-01-01T00:00:00"
        response = client.get(f"/messages/rooms/1?since={since}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_replay_respects_limit(self, client, auth_headers, sample_messages):
        """Should respect the limit parameter."""
        since = "2025-01-01T12:00:00"
        response = client.get(f"/messages/rooms/1?since={since}&limit=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_replay_requires_since_parameter(self, client, auth_headers):
        """Should return 422 when 'since' parameter is missing."""
        response = client.get("/messages/rooms/1", headers=auth_headers)

        assert response.status_code == 422

    def test_replay_rejects_invalid_since_format(self, client, auth_headers):
        """Should return 422 for invalid datetime format."""
        response = client.get("/messages/rooms/1?since=not-a-date", headers=auth_headers)

        assert response.status_code == 422

    def test_replay_response_shape(self, client, auth_headers, sample_messages):
        """Should return messages with the expected schema fields."""
        since = "2025-01-01T12:00:00"
        response = client.get(f"/messages/rooms/1?since={since}&limit=1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        msg = data[0]
        assert "id" in msg
        assert "message_id" in msg
        assert "sender_id" in msg
        assert "room_id" in msg
        assert "content" in msg
        assert "is_private" in msg
        assert "sent_at" in msg


# ══════════════════════════════════════════════════════════════════════
# REST API — History endpoint: GET /messages/rooms/{room_id}/history
# ══════════════════════════════════════════════════════════════════════


class TestHistoryEndpoint:
    """Tests for GET /messages/rooms/{room_id}/history"""

    def test_history_returns_recent_messages(self, client, auth_headers, sample_messages):
        """Should return recent messages in chronological order."""
        response = client.get("/messages/rooms/1/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        # Should be in chronological order (oldest first)
        assert data[0]["content"] == "Test message 0"
        assert data[-1]["content"] == "Test message 4"

    def test_history_returns_empty_for_unknown_room(self, client, auth_headers):
        """Should return empty list for a room with no messages."""
        response = client.get("/messages/rooms/999/history", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_history_respects_custom_limit(self, client, auth_headers, sample_messages):
        """Should respect the limit parameter."""
        response = client.get("/messages/rooms/1/history?limit=3", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should return the 3 most recent, in chronological order
        assert data[0]["content"] == "Test message 2"
        assert data[-1]["content"] == "Test message 4"

    def test_history_default_limit_is_50(self, client, auth_headers, db):
        """Default limit should be 50 — insert 60 messages, expect 50 returned."""
        base_time = datetime(2025, 6, 1, 0, 0, 0)
        for i in range(60):
            db.add(
                Message(
                    message_id=f"bulk-{i:03d}",
                    sender_id=1,
                    room_id=2,
                    content=f"Bulk message {i}",
                    is_private=False,
                    sent_at=base_time + timedelta(minutes=i),
                )
            )
        db.commit()

        response = client.get("/messages/rooms/2/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 50

    def test_history_excludes_private_messages(self, client, auth_headers, db):
        """Private messages should NOT appear in room history."""
        db.add(
            Message(
                message_id="public-msg",
                sender_id=1,
                room_id=3,
                content="Public message",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.add(
            Message(
                message_id="private-msg",
                sender_id=1,
                room_id=3,
                content="Private message",
                is_private=True,
                recipient_id=2,
                sent_at=datetime(2025, 1, 1, 12, 1, 0),
            )
        )
        db.commit()

        response = client.get("/messages/rooms/3/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "Public message"


# ══════════════════════════════════════════════════════════════════════
# Kafka Consumer — Room message persistence
# ══════════════════════════════════════════════════════════════════════


class TestConsumerRoomMessages:
    """Tests for the Kafka consumer's room message persistence."""

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

        import asyncio

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
# Kafka Consumer — Private message persistence
# ══════════════════════════════════════════════════════════════════════


class TestConsumerPrivateMessages:
    """Tests for the Kafka consumer's private message persistence."""

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
# Kafka Consumer — DLQ routing
# ══════════════════════════════════════════════════════════════════════


class TestConsumerDLQ:
    """Tests for the consumer's Dead Letter Queue routing."""

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
# Health endpoints
# ══════════════════════════════════════════════════════════════════════


class TestHealthEndpoints:
    """Tests for /health and /ready endpoints."""

    def test_health_returns_ok(self, client):
        """Liveness probe should always return 200."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_ready_returns_database_status(self, client):
        """Readiness probe should check database connectivity."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "ok"

    def test_ready_includes_kafka_status(self, client):
        """Readiness probe should report Kafka status (non-blocking)."""
        response = client.get("/ready")

        data = response.json()
        assert "kafka" in data


# ══════════════════════════════════════════════════════════════════════
# Authentication
# ══════════════════════════════════════════════════════════════════════


class TestAuthentication:
    """Tests for JWT authentication on message endpoints."""

    def test_valid_token_succeeds(self, client, auth_headers):
        """Request with valid JWT should succeed."""
        response = client.get("/messages/rooms/1/history", headers=auth_headers)

        assert response.status_code == 200

    def test_expired_token_returns_401(self, client, expired_auth_headers):
        """Request with expired JWT should return 401."""
        response = client.get("/messages/rooms/1/history", headers=expired_auth_headers)

        assert response.status_code == 401

    def test_missing_token_returns_401(self, client):
        """Request without Authorization header should return 401."""
        response = client.get("/messages/rooms/1/history")

        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client):
        """Request with malformed JWT should return 401."""
        headers = {"Authorization": "Bearer not-a-valid-jwt"}
        response = client.get("/messages/rooms/1/history", headers=headers)

        assert response.status_code == 401

    def test_replay_requires_auth(self, client):
        """Replay endpoint should require authentication."""
        response = client.get("/messages/rooms/1?since=2025-01-01T00:00:00")

        assert response.status_code == 401
