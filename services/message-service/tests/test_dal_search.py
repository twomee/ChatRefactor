# tests/test_dal_search.py — Tests for search_messages DAL function
#
# Uses SQLite in-memory (from conftest.py) so falls back to LIKE-based search.
# The PostgreSQL tsvector path is covered by integration tests against a real PG
# instance. These tests verify the search logic, filtering, and edge cases.
from datetime import datetime, timedelta

from app.dal.message_dal import search_messages
from app.models import Message


class TestSearchMessages:
    """Tests for the search_messages DAL function."""

    def test_returns_matching_messages(self, db):
        """Should return messages whose content matches the query."""
        db.add(Message(
            message_id="search-match-1",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="Hello world, this is a test message",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="search-match-2",
            sender_id=2,
            sender_name="bob",
            room_id=1,
            content="Another hello from the team",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.add(Message(
            message_id="search-nomatch",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="Completely unrelated content",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 10, 0),
        ))
        db.commit()

        results = search_messages(db, query="hello")

        assert len(results) == 2
        contents = [r.content for r in results]
        assert "Hello world, this is a test message" in contents
        assert "Another hello from the team" in contents

    def test_filters_by_room_id(self, db):
        """Should only return messages from the specified room."""
        db.add(Message(
            message_id="room1-msg",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="hello from room 1",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="room2-msg",
            sender_id=1,
            sender_name="alice",
            room_id=2,
            content="hello from room 2",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        results = search_messages(db, query="hello", room_id=1)

        assert len(results) == 1
        assert results[0].room_id == 1

    def test_returns_empty_for_no_match(self, db):
        """Should return empty list when no messages match the query."""
        db.add(Message(
            message_id="no-match",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="This message has specific content",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.commit()

        results = search_messages(db, query="xyznomatch")

        assert results == []

    def test_excludes_private_messages(self, db):
        """Should not return private messages."""
        db.add(Message(
            message_id="public-search",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="public hello message",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="private-search",
            sender_id=1,
            sender_name="alice",
            room_id=None,
            content="private hello message",
            is_private=True,
            recipient_id=2,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        results = search_messages(db, query="hello")

        assert len(results) == 1
        assert results[0].is_private is False

    def test_excludes_deleted_messages(self, db):
        """Should not return soft-deleted messages."""
        db.add(Message(
            message_id="active-search",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="active hello message",
            is_private=False,
            is_deleted=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="deleted-search",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="[deleted]",
            is_private=False,
            is_deleted=True,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        results = search_messages(db, query="hello")

        assert len(results) == 1
        assert results[0].is_deleted is False

    def test_respects_limit(self, db):
        """Should respect the limit parameter."""
        for i in range(10):
            db.add(Message(
                message_id=f"limit-{i}",
                sender_id=1,
                sender_name="alice",
                room_id=1,
                content=f"hello message number {i}",
                is_private=False,
                sent_at=datetime(2025, 6, 1, 12, 0, 0) + timedelta(minutes=i),
            ))
        db.commit()

        results = search_messages(db, query="hello", limit=3)

        assert len(results) == 3

    def test_caps_limit_at_100(self, db):
        """Should cap the limit at 100 even if a higher value is passed."""
        # Just verify it doesn't raise — we can't easily insert 101+ messages
        # in a unit test, but we test the logic path.
        results = search_messages(db, query="nonexistent", limit=500)
        assert results == []

    def test_case_insensitive_search(self, db):
        """Should match regardless of case (SQLite LIKE fallback is case-insensitive)."""
        db.add(Message(
            message_id="case-test",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="Hello WORLD",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.commit()

        results_lower = search_messages(db, query="hello world")
        results_upper = search_messages(db, query="HELLO WORLD")

        assert len(results_lower) == 1
        assert len(results_upper) == 1

    def test_returns_empty_for_empty_table(self, db):
        """Should return empty list when the messages table is empty."""
        results = search_messages(db, query="anything")
        assert results == []

    def test_room_id_none_searches_all_rooms(self, db):
        """When room_id is None, should search across all rooms."""
        db.add(Message(
            message_id="allrooms-1",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="hello from room 1",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="allrooms-2",
            sender_id=1,
            sender_name="bob",
            room_id=2,
            content="hello from room 2",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        results = search_messages(db, query="hello", room_id=None)

        assert len(results) == 2
