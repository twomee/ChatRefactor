# tests/test_dal_message_dal.py — Tests for app/dal/message_dal.py
#
# Covers:
#   - create_idempotent: insert new, skip duplicate, with/without sent_at
#   - get_by_room_since: filters by room, since timestamp, limit, excludes private
#   - get_room_history: returns recent messages, respects limit, excludes private, order
#   - edit_message: owner can edit, non-owner cannot, deleted messages cannot be edited
#   - soft_delete_message: owner can delete, non-owner cannot, already deleted returns False
#   - delete_all: removes all messages
from datetime import datetime, timedelta

from app.dal.message_dal import (
    create_idempotent,
    delete_all,
    edit_message,
    get_by_room_since,
    get_room_history,
    soft_delete_message,
)
from app.models import Message


class TestCreateIdempotent:
    """Tests for the create_idempotent DAL function."""

    def test_inserts_new_message(self, db):
        """Should insert a new message and return True."""
        result = create_idempotent(
            db,
            message_id="dal-msg-001",
            sender_id=1,
            room_id=1,
            content="Hello from DAL",
        )

        assert result is True
        msg = db.query(Message).filter(Message.message_id == "dal-msg-001").first()
        assert msg is not None
        assert msg.content == "Hello from DAL"
        assert msg.sender_id == 1
        assert msg.room_id == 1
        assert msg.is_private is False

    def test_skips_duplicate_message_id(self, db):
        """Should return False and not insert when message_id already exists."""
        create_idempotent(
            db,
            message_id="dal-msg-dup",
            sender_id=1,
            room_id=1,
            content="First",
        )
        result = create_idempotent(
            db,
            message_id="dal-msg-dup",
            sender_id=2,
            room_id=2,
            content="Duplicate",
        )

        assert result is False
        count = db.query(Message).filter(Message.message_id == "dal-msg-dup").count()
        assert count == 1
        msg = db.query(Message).filter(Message.message_id == "dal-msg-dup").first()
        assert msg.content == "First"  # Original content preserved

    def test_inserts_with_sent_at(self, db):
        """Should use the provided sent_at timestamp."""
        ts = datetime(2025, 6, 15, 10, 30, 0)
        create_idempotent(
            db,
            message_id="dal-msg-ts",
            sender_id=1,
            room_id=1,
            content="With timestamp",
            sent_at=ts,
        )

        msg = db.query(Message).filter(Message.message_id == "dal-msg-ts").first()
        assert msg.sent_at == ts

    def test_inserts_without_sent_at_uses_default(self, db):
        """Should use DB default when sent_at is None."""
        create_idempotent(
            db,
            message_id="dal-msg-nots",
            sender_id=1,
            room_id=1,
            content="No timestamp",
        )

        msg = db.query(Message).filter(Message.message_id == "dal-msg-nots").first()
        assert msg.sent_at is not None

    def test_inserts_private_message(self, db):
        """Should insert a private message with recipient_id."""
        create_idempotent(
            db,
            message_id="dal-pm-001",
            sender_id=1,
            room_id=None,
            content="Private message",
            is_private=True,
            recipient_id=2,
        )

        msg = db.query(Message).filter(Message.message_id == "dal-pm-001").first()
        assert msg is not None
        assert msg.is_private is True
        assert msg.recipient_id == 2
        assert msg.room_id is None


class TestGetByRoomSince:
    """Tests for the get_by_room_since DAL function."""

    def test_returns_messages_after_timestamp(self, db):
        """Should return only messages sent after the given timestamp."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        for i in range(5):
            db.add(
                Message(
                    message_id=f"since-{i}",
                    sender_id=1,
                    room_id=1,
                    content=f"Message {i}",
                    is_private=False,
                    sent_at=base + timedelta(minutes=i),
                )
            )
        db.commit()

        result = get_by_room_since(db, room_id=1, since=base + timedelta(minutes=2))

        assert len(result) == 3  # Messages at 12:02, 12:03, 12:04
        assert result[0].content == "Message 2"

    def test_filters_by_room_id(self, db):
        """Should only return messages from the specified room."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        db.add(
            Message(
                message_id="r1",
                sender_id=1,
                room_id=1,
                content="Room 1",
                is_private=False,
                sent_at=base,
            )
        )
        db.add(
            Message(
                message_id="r2",
                sender_id=1,
                room_id=2,
                content="Room 2",
                is_private=False,
                sent_at=base,
            )
        )
        db.commit()

        result = get_by_room_since(db, room_id=1, since=base - timedelta(hours=1))

        assert len(result) == 1
        assert result[0].content == "Room 1"

    def test_excludes_private_messages(self, db):
        """Should not return private messages."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        db.add(
            Message(
                message_id="pub",
                sender_id=1,
                room_id=1,
                content="Public",
                is_private=False,
                sent_at=base,
            )
        )
        db.add(
            Message(
                message_id="priv",
                sender_id=1,
                room_id=1,
                content="Private",
                is_private=True,
                sent_at=base,
            )
        )
        db.commit()

        result = get_by_room_since(db, room_id=1, since=base - timedelta(hours=1))

        assert len(result) == 1
        assert result[0].content == "Public"

    def test_respects_limit(self, db):
        """Should respect the limit parameter."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        for i in range(10):
            db.add(
                Message(
                    message_id=f"lim-{i}",
                    sender_id=1,
                    room_id=1,
                    content=f"Message {i}",
                    is_private=False,
                    sent_at=base + timedelta(minutes=i),
                )
            )
        db.commit()

        result = get_by_room_since(
            db, room_id=1, since=base - timedelta(hours=1), limit=3
        )

        assert len(result) == 3

    def test_orders_by_sent_at_ascending(self, db):
        """Should return messages in chronological order (oldest first)."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        db.add(
            Message(
                message_id="late",
                sender_id=1,
                room_id=1,
                content="Late",
                is_private=False,
                sent_at=base + timedelta(minutes=5),
            )
        )
        db.add(
            Message(
                message_id="early",
                sender_id=1,
                room_id=1,
                content="Early",
                is_private=False,
                sent_at=base,
            )
        )
        db.commit()

        result = get_by_room_since(db, room_id=1, since=base - timedelta(hours=1))

        assert result[0].content == "Early"
        assert result[1].content == "Late"

    def test_returns_empty_for_no_matches(self, db):
        """Should return empty list when no messages match."""
        result = get_by_room_since(db, room_id=999, since=datetime(2025, 1, 1))

        assert result == []


class TestGetRoomHistory:
    """Tests for the get_room_history DAL function."""

    def test_returns_recent_messages_in_chronological_order(self, db):
        """Should return the most recent messages, ordered oldest-first."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        for i in range(5):
            db.add(
                Message(
                    message_id=f"hist-{i}",
                    sender_id=1,
                    room_id=1,
                    content=f"Message {i}",
                    is_private=False,
                    sent_at=base + timedelta(minutes=i),
                )
            )
        db.commit()

        result = get_room_history(db, room_id=1, limit=3)

        assert len(result) == 3
        # Should be the 3 most recent, in chronological order
        assert result[0].content == "Message 2"
        assert result[1].content == "Message 3"
        assert result[2].content == "Message 4"

    def test_excludes_private_messages(self, db):
        """Should not return private messages."""
        base = datetime(2025, 1, 1, 12, 0, 0)
        db.add(
            Message(
                message_id="pub-h",
                sender_id=1,
                room_id=1,
                content="Public",
                is_private=False,
                sent_at=base,
            )
        )
        db.add(
            Message(
                message_id="priv-h",
                sender_id=1,
                room_id=1,
                content="Private",
                is_private=True,
                sent_at=base,
            )
        )
        db.commit()

        result = get_room_history(db, room_id=1)

        assert len(result) == 1
        assert result[0].content == "Public"

    def test_returns_empty_for_unknown_room(self, db):
        """Should return empty list for a room with no messages."""
        result = get_room_history(db, room_id=999)

        assert result == []


class TestEditMessage:
    """Tests for the edit_message DAL function."""

    def test_edit_succeeds_for_owner(self, db):
        """Owner should be able to edit their own message."""
        create_idempotent(
            db, message_id="edit-001", sender_id=1, room_id=1, content="Original"
        )

        result = edit_message(db, "edit-001", sender_id=1, new_content="Updated")

        assert result is True
        msg = db.query(Message).filter(Message.message_id == "edit-001").first()
        assert msg.content == "Updated"
        assert msg.edited_at is not None

    def test_edit_returns_false_for_non_owner(self, db):
        """Non-owner should not be able to edit another user's message."""
        create_idempotent(
            db, message_id="edit-002", sender_id=1, room_id=1, content="Original"
        )

        result = edit_message(db, "edit-002", sender_id=2, new_content="Hacked")

        assert result is False
        msg = db.query(Message).filter(Message.message_id == "edit-002").first()
        assert msg.content == "Original"  # Content unchanged

    def test_edit_returns_false_for_deleted_message(self, db):
        """Should not be able to edit a deleted message."""
        create_idempotent(
            db, message_id="edit-003", sender_id=1, room_id=1, content="Original"
        )
        soft_delete_message(db, "edit-003", sender_id=1)

        result = edit_message(db, "edit-003", sender_id=1, new_content="Updated")

        assert result is False

    def test_edit_returns_false_for_nonexistent_message(self, db):
        """Should return False for a message that doesn't exist."""
        result = edit_message(db, "nonexistent", sender_id=1, new_content="Updated")

        assert result is False


class TestSoftDeleteMessage:
    """Tests for the soft_delete_message DAL function."""

    def test_delete_succeeds_for_owner(self, db):
        """Owner should be able to soft-delete their own message."""
        create_idempotent(
            db, message_id="del-001", sender_id=1, room_id=1, content="To be deleted"
        )

        result = soft_delete_message(db, "del-001", sender_id=1)

        assert result is True
        msg = db.query(Message).filter(Message.message_id == "del-001").first()
        assert msg.is_deleted is True
        assert msg.content == "[deleted]"

    def test_delete_returns_false_for_non_owner(self, db):
        """Non-owner should not be able to delete another user's message."""
        create_idempotent(
            db, message_id="del-002", sender_id=1, room_id=1, content="Protected"
        )

        result = soft_delete_message(db, "del-002", sender_id=2)

        assert result is False
        msg = db.query(Message).filter(Message.message_id == "del-002").first()
        assert msg.is_deleted is False
        assert msg.content == "Protected"

    def test_delete_returns_false_for_already_deleted(self, db):
        """Should return False if the message is already deleted."""
        create_idempotent(
            db, message_id="del-003", sender_id=1, room_id=1, content="Delete me"
        )
        soft_delete_message(db, "del-003", sender_id=1)

        result = soft_delete_message(db, "del-003", sender_id=1)

        assert result is False

    def test_delete_returns_false_for_nonexistent_message(self, db):
        """Should return False for a message that doesn't exist."""
        result = soft_delete_message(db, "nonexistent", sender_id=1)

        assert result is False


class TestDeleteAll:
    """Tests for the delete_all DAL function."""

    def test_deletes_all_messages(self, db):
        """Should remove all messages from the database."""
        db.add(
            Message(
                message_id="del-1",
                sender_id=1,
                room_id=1,
                content="A",
                is_private=False,
            )
        )
        db.add(
            Message(
                message_id="del-2",
                sender_id=1,
                room_id=1,
                content="B",
                is_private=False,
            )
        )
        db.commit()

        assert db.query(Message).count() == 2

        delete_all(db)

        assert db.query(Message).count() == 0

    def test_delete_all_on_empty_table(self, db):
        """Should not raise when table is already empty."""
        delete_all(db)  # Should not raise
        assert db.query(Message).count() == 0
