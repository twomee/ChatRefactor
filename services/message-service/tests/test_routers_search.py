# tests/test_routers_search.py — Tests for GET /messages/search endpoint
#
# Covers:
#   - Basic search returns matching messages
#   - Room filter works
#   - Empty query validation
#   - Auth required
#   - Response shape
#   - Limit parameter
from datetime import datetime, timedelta

from app.models import Message


class TestSearchEndpoint:
    """Tests for GET /messages/search?q=..."""

    def test_search_returns_matching_messages(self, client, auth_headers, db):
        """Should return messages matching the search query."""
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

        response = client.get("/messages/search?q=hello", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "Hello world from alice"

    def test_search_with_room_filter(self, client, auth_headers, db):
        """Should filter results by room_id when provided."""
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
        response = client.get("/messages/search?q=xyznomatch", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_search_requires_auth(self, client):
        """Search endpoint should require authentication."""
        response = client.get("/messages/search?q=hello")

        assert response.status_code == 401

    def test_search_requires_query_parameter(self, client, auth_headers):
        """Should return 422 when q parameter is missing."""
        response = client.get("/messages/search", headers=auth_headers)

        assert response.status_code == 422

    def test_search_rejects_whitespace_only_query(self, client, auth_headers):
        """Should return 400 for whitespace-only query."""
        response = client.get("/messages/search?q=%20%20%20", headers=auth_headers)

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

        response = client.get("/messages/search?q=shape", headers=auth_headers)

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

        response = client.get("/messages/search?q=searchable&limit=3", headers=auth_headers)

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

        response = client.get("/messages/search?q=searchable", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["message_id"] == "pub-srch"

    def test_search_limit_validation(self, client, auth_headers):
        """Should return 422 for limit exceeding max or below min."""
        response = client.get("/messages/search?q=test&limit=101", headers=auth_headers)
        assert response.status_code == 422

        response = client.get("/messages/search?q=test&limit=0", headers=auth_headers)
        assert response.status_code == 422
