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
# PM reaction persistence via _process
# ══════════════════════════════════════════════════════════════════════


class TestPMReactionPersistence:
    """Tests that add_pm_reaction / remove_pm_reaction events on TOPIC_PRIVATE
    are persisted to the reactions table (bug fix: they were silently dropped
    because the TOPIC_PRIVATE branch only handled private_message events)."""

    @pytest.mark.asyncio
    async def test_add_pm_reaction_persisted(self, db, consumer, monkeypatch):
        """add_pm_reaction event should write a row to the reactions table."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        await consumer._process(
            TOPIC_PRIVATE,
            {
                "type": "add_pm_reaction",
                "msg_id": "pm-1-2-9999",
                "emoji": "👍",
                "reactor_id": 1,
                "reactor": "alice",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        from app.dal import reaction_dal

        reactions = reaction_dal.get_reactions_for_messages(db, ["pm-1-2-9999"])
        assert "pm-1-2-9999" in reactions
        assert any(r["emoji"] == "👍" for r in reactions["pm-1-2-9999"])

    @pytest.mark.asyncio
    async def test_remove_pm_reaction_persisted(self, db, consumer, monkeypatch):
        """remove_pm_reaction event should delete the reaction from the DB."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        # First add, then remove.
        await consumer._process(
            TOPIC_PRIVATE,
            {
                "type": "add_pm_reaction",
                "msg_id": "pm-1-2-8888",
                "emoji": "❤️",
                "reactor_id": 2,
                "reactor": "bob",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await consumer._process(
            TOPIC_PRIVATE,
            {
                "type": "remove_pm_reaction",
                "msg_id": "pm-1-2-8888",
                "emoji": "❤️",
                "reactor_id": 2,
                "reactor": "bob",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        from app.dal import reaction_dal

        reactions = reaction_dal.get_reactions_for_messages(db, ["pm-1-2-8888"])
        assert not reactions.get("pm-1-2-8888")  # removed

    @pytest.mark.asyncio
    async def test_private_message_still_dispatched(self, db, consumer, monkeypatch):
        """Existing private_message type on TOPIC_PRIVATE still routes correctly."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        mock_sender = {"id": 10, "username": "alice"}
        mock_recipient = {"id": 20, "username": "bob"}

        with patch("app.consumers.persistence_consumer.get_user_by_username") as mock_get:
            mock_get.side_effect = lambda name: {
                "alice": mock_sender,
                "bob": mock_recipient,
            }.get(name)

            await consumer._process(
                TOPIC_PRIVATE,
                {
                    "msg_id": "pm-dispatch-after-fix",
                    "sender": "alice",
                    "recipient": "bob",
                    "text": "Still works",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        msg = db.query(Message).filter(Message.message_id == "pm-dispatch-after-fix").first()
        assert msg is not None
        assert msg.content == "Still works"


# ══════════════════════════════════════════════════════════════════════
# DLQ routing via _process_with_retry
# ══════════════════════════════════════════════════════════════════════


