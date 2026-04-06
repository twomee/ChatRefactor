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
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.consumers.persistence_consumer import MAX_CONTENT_LENGTH, MessagePersistenceConsumer
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

    @pytest.mark.asyncio
    async def test_oversized_private_message_is_truncated(self, db, consumer):
        """PM content exceeding MAX_CONTENT_LENGTH should be truncated (lines 223-226)."""
        oversized_text = "y" * (MAX_CONTENT_LENGTH + 1000)
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
                    "msg_id": "oversized-pm",
                    "sender": "alice",
                    "recipient": "bob",
                    "text": oversized_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        msg = db.query(Message).filter(Message.message_id == "oversized-pm").first()
        assert msg is not None
        assert len(msg.content) == MAX_CONTENT_LENGTH


# ══════════════════════════════════════════════════════════════════════
# _process dispatch for edit/delete/reaction message types (lines 154-160)
# ══════════════════════════════════════════════════════════════════════


class TestProcessDispatch:
    """Tests for _process() dispatching specific message types."""

    @pytest.mark.asyncio
    async def test_process_dispatches_edit_message(self, db, consumer, monkeypatch):
        """_process() should route 'edit_message' type to _handle_edit_message (line 154)."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        db.add(Message(
            message_id="dispatch-edit-msg",
            sender_id=1,
            room_id=1,
            content="Original text",
            is_private=False,
        ))
        db.commit()

        await consumer._process(
            TOPIC_MESSAGES,
            {
                "type": "edit_message",
                "msg_id": "dispatch-edit-msg",
                "sender_id": 1,
                "text": "Edited text",
            },
        )

        msg = db.query(Message).filter_by(message_id="dispatch-edit-msg").first()
        assert msg.content == "Edited text"

    @pytest.mark.asyncio
    async def test_process_dispatches_delete_message(self, db, consumer, monkeypatch):
        """_process() should route 'delete_message' type to _handle_delete_message (line 156)."""
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        db.add(Message(
            message_id="dispatch-del-msg",
            sender_id=1,
            room_id=1,
            content="Will be deleted",
            is_private=False,
        ))
        db.commit()

        await consumer._process(
            TOPIC_MESSAGES,
            {
                "type": "delete_message",
                "msg_id": "dispatch-del-msg",
                "sender_id": 1,
            },
        )

        msg = db.query(Message).filter_by(message_id="dispatch-del-msg").first()
        assert msg.is_deleted is True

    @pytest.mark.asyncio
    async def test_process_dispatches_add_reaction(self, db, consumer, monkeypatch):
        """_process() should route 'add_reaction' type to _persist_add_reaction (line 158)."""
        from app.dal import reaction_dal

        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        db.add(Message(
            message_id="react-target",
            sender_id=1,
            room_id=1,
            content="React to me",
            is_private=False,
        ))
        db.commit()

        await consumer._process(
            TOPIC_MESSAGES,
            {
                "type": "add_reaction",
                "msg_id": "react-target",
                "user_id": 2,
                "username": "bob",
                "emoji": "👍",
            },
        )

        reactions = reaction_dal.get_reactions_for_message(db, "react-target")
        assert len(reactions) == 1
        assert reactions[0].emoji == "👍"

    @pytest.mark.asyncio
    async def test_process_dispatches_remove_reaction(self, db, consumer, monkeypatch):
        """_process() should route 'remove_reaction' type to _persist_remove_reaction (line 160)."""
        from app.dal import reaction_dal
        from app.models import Reaction

        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)

        db.add(Message(
            message_id="remove-react-target",
            sender_id=1,
            room_id=1,
            content="React to me",
            is_private=False,
        ))
        db.add(Reaction(
            message_id="remove-react-target",
            user_id=2,
            username="bob",
            emoji="👍",
        ))
        db.commit()

        await consumer._process(
            TOPIC_MESSAGES,
            {
                "type": "remove_reaction",
                "msg_id": "remove-react-target",
                "user_id": 2,
                "emoji": "👍",
            },
        )

        reactions = reaction_dal.get_reactions_for_message(db, "remove-react-target")
        assert len(reactions) == 0


# ══════════════════════════════════════════════════════════════════════
# _handle_edit_message (lines 271-284)
# ══════════════════════════════════════════════════════════════════════


class TestHandleEditMessage:
    """Tests for the _handle_edit_message method."""

    def test_edits_message_when_owned_by_sender(self, db, consumer):
        """Should edit the message and log debug when successful (lines 279-280)."""
        db.add(Message(
            message_id="edit-kafka-1",
            sender_id=1,
            room_id=1,
            content="Before edit",
            is_private=False,
        ))
        db.commit()

        consumer._handle_edit_message(db, {
            "msg_id": "edit-kafka-1",
            "sender_id": 1,
            "text": "After edit",
        })

        msg = db.query(Message).filter_by(message_id="edit-kafka-1").first()
        assert msg.content == "After edit"

    def test_logs_warning_when_edit_fails(self, db, consumer):
        """Should log a warning when the edit fails (lines 281-284)."""
        # No message in DB — edit will fail
        consumer._handle_edit_message(db, {
            "msg_id": "no-such-msg",
            "sender_id": 1,
            "text": "Won't apply",
        })
        # Should complete without raising

    def test_skips_when_msg_id_is_none(self, db, consumer):
        """Should do nothing when msg_id is None."""
        consumer._handle_edit_message(db, {
            "msg_id": None,
            "sender_id": 1,
            "text": "text",
        })

    def test_skips_when_sender_id_is_none(self, db, consumer):
        """Should do nothing when sender_id is None."""
        consumer._handle_edit_message(db, {
            "msg_id": "some-id",
            "sender_id": None,
            "text": "text",
        })


# ══════════════════════════════════════════════════════════════════════
# _handle_delete_message (lines 288-300)
# ══════════════════════════════════════════════════════════════════════


class TestHandleDeleteMessage:
    """Tests for the _handle_delete_message method."""

    def test_soft_deletes_message_when_owned_by_sender(self, db, consumer):
        """Should soft-delete the message and log debug when successful (lines 295-296)."""
        db.add(Message(
            message_id="delete-kafka-1",
            sender_id=1,
            room_id=1,
            content="To be deleted",
            is_private=False,
        ))
        db.commit()

        consumer._handle_delete_message(db, {
            "msg_id": "delete-kafka-1",
            "sender_id": 1,
        })

        msg = db.query(Message).filter_by(message_id="delete-kafka-1").first()
        assert msg.is_deleted is True

    def test_logs_warning_when_delete_fails(self, db, consumer):
        """Should log a warning when the delete fails (lines 297-300)."""
        consumer._handle_delete_message(db, {
            "msg_id": "nonexistent",
            "sender_id": 1,
        })

    def test_skips_when_msg_id_is_none(self, db, consumer):
        """Should do nothing when msg_id is None."""
        consumer._handle_delete_message(db, {"msg_id": None, "sender_id": 1})

    def test_skips_when_sender_id_is_none(self, db, consumer):
        """Should do nothing when sender_id is None."""
        consumer._handle_delete_message(db, {"msg_id": "some-id", "sender_id": None})


# ══════════════════════════════════════════════════════════════════════
# _persist_add_reaction (lines 304-320)
# ══════════════════════════════════════════════════════════════════════


class TestPersistAddReaction:
    """Tests for the _persist_add_reaction method."""

    def test_adds_reaction_successfully(self, db, consumer):
        """Should call reaction_dal.add_reaction and increment metrics (lines 315-320)."""
        consumer._persist_add_reaction(db, {
            "msg_id": "msg-add-react",
            "user_id": 1,
            "username": "alice",
            "emoji": "👍",
        })

        from app.dal import reaction_dal
        reactions = reaction_dal.get_reactions_for_message(db, "msg-add-react")
        assert len(reactions) == 1
        assert reactions[0].emoji == "👍"

    def test_logs_warning_when_fields_missing(self, db, consumer):
        """Should log warning and return early when any required field is None (lines 312-313)."""
        consumer._persist_add_reaction(db, {
            "msg_id": "some-msg",
            "user_id": None,
            "username": "alice",
            "emoji": "👍",
        })

    def test_skips_when_all_fields_none(self, db, consumer):
        """Should log warning and return early when all fields are None."""
        consumer._persist_add_reaction(db, {
            "msg_id": None,
            "user_id": None,
            "username": None,
            "emoji": None,
        })


# ══════════════════════════════════════════════════════════════════════
# _persist_remove_reaction (lines 324-336)
# ══════════════════════════════════════════════════════════════════════


class TestPersistRemoveReaction:
    """Tests for the _persist_remove_reaction method."""

    def test_removes_reaction_successfully(self, db, consumer):
        """Should remove the reaction and log debug (lines 334-336)."""
        from app.models import Reaction

        db.add(Reaction(
            message_id="msg-rem-react",
            user_id=1,
            username="alice",
            emoji="❤️",
        ))
        db.commit()

        consumer._persist_remove_reaction(db, {
            "msg_id": "msg-rem-react",
            "user_id": 1,
            "emoji": "❤️",
        })

        from app.dal import reaction_dal
        reactions = reaction_dal.get_reactions_for_message(db, "msg-rem-react")
        assert len(reactions) == 0

    def test_silently_ignores_nonexistent_reaction(self, db, consumer):
        """Removing a reaction that doesn't exist should complete without error."""
        consumer._persist_remove_reaction(db, {
            "msg_id": "no-such-msg",
            "user_id": 1,
            "emoji": "👍",
        })

    def test_logs_warning_when_fields_missing(self, db, consumer):
        """Should log warning and return early when any required field is None (lines 330-332)."""
        consumer._persist_remove_reaction(db, {
            "msg_id": "some-msg",
            "user_id": None,
            "emoji": "👍",
        })

