# tests/test_routers_messages.py — Tests for app/routers/messages.py
#
# Covers:
#   - GET /messages/rooms/{id}?since=...&limit=... (replay endpoint)
#   - GET /messages/rooms/{id}/history (history endpoint)
#   - Auth: valid token, invalid token, expired token, missing token
#   - API input validation (negative room_id, limit exceeding max, limit zero)
from datetime import datetime, timedelta

import pytest

from app.models import Message


# ══════════════════════════════════════════════════════════════════════
# REST API — Replay endpoint: GET /messages/rooms/{room_id}?since=...
# ══════════════════════════════════════════════════════════════════════


class TestReplayEndpoint:
    """Tests for GET /messages/rooms/{room_id}?since=...&limit=..."""

    def test_replay_returns_messages_since_timestamp(
        self, client, auth_headers, sample_messages
    ):
        """Should return messages after the given timestamp."""
        since = "2025-01-01T12:02:00"
        response = client.get(
            f"/messages/rooms/1?since={since}&limit=100", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Messages at 12:02, 12:03, 12:04 should be returned (3 messages)
        assert len(data) == 3
        assert data[0]["content"] == "Test message 2"
        assert data[-1]["content"] == "Test message 4"

    def test_replay_returns_empty_list_when_no_messages(self, client, auth_headers):
        """Should return empty list for a room with no messages."""
        since = "2025-01-01T00:00:00"
        response = client.get(
            f"/messages/rooms/999?since={since}", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_replay_returns_empty_when_since_is_after_all_messages(
        self, client, auth_headers, sample_messages
    ):
        """Should return empty list when 'since' is after all messages."""
        since = "2026-01-01T00:00:00"
        response = client.get(f"/messages/rooms/1?since={since}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_replay_respects_limit(self, client, auth_headers, sample_messages):
        """Should respect the limit parameter."""
        since = "2025-01-01T12:00:00"
        response = client.get(
            f"/messages/rooms/1?since={since}&limit=2", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_replay_requires_since_parameter(self, client, auth_headers):
        """Should return 422 when 'since' parameter is missing."""
        response = client.get("/messages/rooms/1", headers=auth_headers)

        assert response.status_code == 422

    def test_replay_rejects_invalid_since_format(self, client, auth_headers):
        """Should return 422 for invalid datetime format."""
        response = client.get(
            "/messages/rooms/1?since=not-a-date", headers=auth_headers
        )

        assert response.status_code == 422

    def test_replay_response_shape(self, client, auth_headers, sample_messages):
        """Should return messages with the expected schema fields."""
        since = "2025-01-01T12:00:00"
        response = client.get(
            f"/messages/rooms/1?since={since}&limit=1", headers=auth_headers
        )

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

    def test_replay_requires_auth(self, client):
        """Replay endpoint should require authentication."""
        response = client.get("/messages/rooms/1?since=2025-01-01T00:00:00")

        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# REST API — History endpoint: GET /messages/rooms/{room_id}/history
# ══════════════════════════════════════════════════════════════════════


class TestHistoryEndpoint:
    """Tests for GET /messages/rooms/{room_id}/history"""

    def test_history_returns_recent_messages(
        self, client, auth_headers, sample_messages
    ):
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
        """Default limit should be 50 -- insert 60 messages, expect 50 returned."""
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


# ══════════════════════════════════════════════════════════════════════
# API input validation
# ══════════════════════════════════════════════════════════════════════


class TestAPIInputValidation:
    """Tests for API parameter validation."""

    def test_negative_room_id_returns_422_or_empty(self, client, auth_headers):
        """Negative room_id should be handled safely (no SQL injection)."""
        response = client.get("/messages/rooms/-1/history", headers=auth_headers)
        # Should succeed (just returns empty) since -1 is a valid int
        assert response.status_code == 200
        assert response.json() == []

    def test_limit_exceeding_max_returns_422(self, client, auth_headers):
        """Limit exceeding the maximum should return 422 validation error."""
        response = client.get(
            "/messages/rooms/1?since=2025-01-01T00:00:00&limit=501",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_zero_returns_422(self, client, auth_headers):
        """Limit of 0 should return 422 validation error."""
        response = client.get(
            "/messages/rooms/1?since=2025-01-01T00:00:00&limit=0",
            headers=auth_headers,
        )
        assert response.status_code == 422
