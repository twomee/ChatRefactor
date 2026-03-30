# tests/test_routers_search.py — Tests for GET /messages/search endpoint
#
# Covers:
#   - Basic search returns matching messages
#   - Room filter is required (Fix 2 — cross-room enumeration prevention)
#   - Empty query validation
#   - Auth required
#   - Response shape
#   - Limit parameter
#   - min_length=2 enforcement (Fix 3)
from datetime import datetime, timedelta

from app.models import Message


class TestSearchEndpoint:
    """Tests for GET /messages/search?q=...&room_id=..."""

    def test_search_returns_matching_messages(self, client, auth_headers, db):
        """Should return messages matching the search query within the given room."""
        db.add(Message(
            message_id="srch-1",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="Hello world from alice",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="srch-2",
            sender_id=2,
            sender_name="bob",
            room_id=1,
            content="Goodbye world from bob",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        response = client.get("/messages/search?q=hello&room_id=1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "Hello world from alice"

    def test_search_without_room_id_searches_all_rooms(self, client, auth_headers, db):
        """room_id is optional — omitting it searches across all rooms."""
        db.add(Message(
            message_id="no-room-id-test",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="hello message",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.commit()

        response = client.get("/messages/search?q=hello", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["content"] == "hello message"

    def test_search_scoped_to_room(self, client, auth_headers, db):
        """Should only return messages from the requested room, not all rooms."""
        db.add(Message(
            message_id="room-srch-1",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="hello from room 1",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="room-srch-2",
            sender_id=1,
            sender_name="alice",
            room_id=2,
            content="hello from room 2",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        response = client.get("/messages/search?q=hello&room_id=1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["room_id"] == 1

    def test_search_returns_empty_for_no_match(self, client, auth_headers):
        """Should return empty list when no messages match."""
        response = client.get(
            "/messages/search?q=xyznomatch&room_id=1", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_search_requires_auth(self, client):
        """Search endpoint should require authentication."""
        response = client.get("/messages/search?q=hello&room_id=1")

        assert response.status_code == 401

    def test_search_requires_query_parameter(self, client, auth_headers):
        """Should return 422 when q parameter is missing."""
        response = client.get("/messages/search?room_id=1", headers=auth_headers)

        assert response.status_code == 422

    def test_search_rejects_single_char_query(self, client, auth_headers):
        """min_length=2 — single-character queries must return 422 (prevents full GIN scans)."""
        response = client.get("/messages/search?q=a&room_id=1", headers=auth_headers)

        assert response.status_code == 422

    def test_search_rejects_whitespace_only_query(self, client, auth_headers):
        """Should return 400 for whitespace-only query."""
        response = client.get(
            "/messages/search?q=%20%20%20&room_id=1", headers=auth_headers
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_response_shape(self, client, auth_headers, db):
        """Should return messages with the expected fields."""
        db.add(Message(
            message_id="shape-1",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="test message for shape check",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.commit()

        response = client.get(
            "/messages/search?q=shape&room_id=1", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        msg = data[0]
        assert "message_id" in msg
        assert "sender_name" in msg
        assert "content" in msg
        assert "room_id" in msg
        assert "sent_at" in msg

    def test_search_respects_limit(self, client, auth_headers, db):
        """Should respect the limit parameter."""
        for i in range(10):
            db.add(Message(
                message_id=f"limit-srch-{i}",
                sender_id=1,
                sender_name="alice",
                room_id=1,
                content=f"searchable message {i}",
                is_private=False,
                sent_at=datetime(2025, 6, 1, 12, 0, 0) + timedelta(minutes=i),
            ))
        db.commit()

        response = client.get(
            "/messages/search?q=searchable&room_id=1&limit=3", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_search_excludes_private_messages(self, client, auth_headers, db):
        """Private messages should not appear in search results."""
        db.add(Message(
            message_id="pub-srch",
            sender_id=1,
            sender_name="alice",
            room_id=1,
            content="public searchable message",
            is_private=False,
            sent_at=datetime(2025, 6, 1, 12, 0, 0),
        ))
        db.add(Message(
            message_id="priv-srch",
            sender_id=1,
            sender_name="alice",
            room_id=None,
            content="private searchable message",
            is_private=True,
            recipient_id=2,
            sent_at=datetime(2025, 6, 1, 12, 5, 0),
        ))
        db.commit()

        response = client.get(
            "/messages/search?q=searchable&room_id=1", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["message_id"] == "pub-srch"

    def test_search_limit_validation(self, client, auth_headers):
        """Should return 422 for limit exceeding max or below min."""
        response = client.get(
            "/messages/search?q=test&room_id=1&limit=101", headers=auth_headers
        )
        assert response.status_code == 422

        response = client.get(
            "/messages/search?q=test&room_id=1&limit=0", headers=auth_headers
        )
        assert response.status_code == 422

    def test_search_respects_clear_history(self, client, auth_headers, db):
        """Messages sent before the user's clear timestamp must not appear in search results."""
        from app.models import UserMessageClear

        base_time = datetime(2025, 7, 1, 10, 0, 0)
        clear_time = datetime(2025, 7, 1, 11, 0, 0)

        db.add(Message(
            message_id="clr-srch-old",
            sender_id=1, sender_name="alice", room_id=10,
            content="cleartest keyword old",
            is_private=False, sent_at=base_time,
        ))
        db.add(Message(
            message_id="clr-srch-new",
            sender_id=1, sender_name="alice", room_id=10,
            content="cleartest keyword new",
            is_private=False, sent_at=base_time + timedelta(hours=2),
        ))
        # user_id=1 (matches auth_headers fixture) clears room 10 at clear_time
        db.add(UserMessageClear(
            user_id=1, context_type="room", context_id=10, cleared_at=clear_time,
        ))
        db.commit()

        response = client.get(
            "/messages/search?q=cleartest+keyword&room_id=10", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        ids = [m["message_id"] for m in data]
        assert "clr-srch-old" not in ids, "pre-clear message should be hidden"
        assert "clr-srch-new" in ids, "post-clear message should be visible"

    def test_search_without_room_id_respects_cross_room_clear_filter(
        self, client, auth_headers, db
    ):
        """When room_id is omitted, search must still hide cleared messages from any room."""
        from app.models import UserMessageClear

        base_time = datetime(2025, 8, 1, 10, 0, 0)
        clear_time = datetime(2025, 8, 1, 11, 0, 0)

        # Two messages in room 20 — one before clear, one after
        db.add(Message(
            message_id="xroom-old", sender_id=1, sender_name="alice", room_id=20,
            content="crossroom keyword old", is_private=False, sent_at=base_time,
        ))
        db.add(Message(
            message_id="xroom-new", sender_id=1, sender_name="alice", room_id=20,
            content="crossroom keyword new", is_private=False,
            sent_at=base_time + timedelta(hours=2),
        ))
        # Message in room 21 (not cleared) — should always be visible
        db.add(Message(
            message_id="xroom-uncleared", sender_id=1, sender_name="alice", room_id=21,
            content="crossroom keyword other", is_private=False, sent_at=base_time,
        ))
        db.add(UserMessageClear(
            user_id=1, context_type="room", context_id=20, cleared_at=clear_time,
        ))
        db.commit()

        # Search across all rooms (no room_id)
        response = client.get(
            "/messages/search?q=crossroom+keyword", headers=auth_headers
        )

        assert response.status_code == 200
        ids = [m["message_id"] for m in response.json()]
        assert "xroom-old" not in ids, "pre-clear message in cleared room should be hidden"
        assert "xroom-new" in ids, "post-clear message in cleared room should be visible"
        assert "xroom-uncleared" in ids, "message in uncleared room should be visible"
