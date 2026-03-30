# tests/test_routers_messages.py — Tests for app/routers/messages.py
#
# Covers:
#   - GET /messages/rooms/{id}?since=...&limit=... (replay endpoint)
#   - GET /messages/rooms/{id}/history (history endpoint)
#   - PATCH /messages/edit/{message_id} (edit endpoint)
#   - DELETE /messages/delete/{message_id} (delete endpoint)
#   - GET /messages/{message_id}/reactions (reactions endpoint)
#   - Auth: valid token, invalid token, expired token, missing token
#   - API input validation (negative room_id, limit exceeding max, limit zero)
from datetime import datetime, timedelta

import pytest

from app.models import Message, Reaction


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

    def test_replay_requires_auth(self, client):
        """Replay endpoint should require authentication."""
        response = client.get("/messages/rooms/1?since=2025-01-01T00:00:00")

        assert response.status_code == 401


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
        response = client.get(
            "/messages/rooms/-1/history", headers=auth_headers
        )
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


# ══════════════════════════════════════════════════════════════════════
# Edit endpoint: PATCH /messages/edit/{message_id}
# ══════════════════════════════════════════════════════════════════════


class TestEditMessageEndpoint:
    """Tests for PATCH /messages/edit/{message_id}."""

    def test_edit_returns_200_for_own_message(self, client, auth_headers, db):
        """Sender should be able to edit their own message."""
        db.add(
            Message(
                message_id="edit-owned",
                sender_id=1,
                room_id=1,
                content="Original content",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.patch(
            "/messages/edit/edit-owned",
            json={"content": "Updated content"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"edited": True}

    def test_edit_returns_404_for_nonexistent_message(self, client, auth_headers):
        """Editing a message that does not exist should return 404."""
        response = client.patch(
            "/messages/edit/does-not-exist",
            json={"content": "New content"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_edit_returns_404_for_message_owned_by_another_user(
        self, client, auth_headers, db
    ):
        """Editing a message owned by a different user should return 404."""
        # sender_id=99 — not the authenticated user (user_id=1)
        db.add(
            Message(
                message_id="edit-other",
                sender_id=99,
                room_id=1,
                content="Someone else's message",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.patch(
            "/messages/edit/edit-other",
            json={"content": "Attempted hijack"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_edit_returns_404_for_already_deleted_message(
        self, client, auth_headers, db
    ):
        """Editing a soft-deleted message should return 404."""
        db.add(
            Message(
                message_id="edit-deleted",
                sender_id=1,
                room_id=1,
                content="[deleted]",
                is_private=False,
                is_deleted=True,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.patch(
            "/messages/edit/edit-deleted",
            json={"content": "Try to restore"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_edit_requires_auth(self, client):
        """Edit endpoint must require authentication."""
        response = client.patch(
            "/messages/edit/some-id",
            json={"content": "content"},
        )
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# Delete endpoint: DELETE /messages/delete/{message_id}
# ══════════════════════════════════════════════════════════════════════


class TestDeleteMessageEndpoint:
    """Tests for DELETE /messages/delete/{message_id}."""

    def test_delete_returns_200_for_own_message(self, client, auth_headers, db):
        """Sender should be able to soft-delete their own message."""
        db.add(
            Message(
                message_id="del-owned",
                sender_id=1,
                room_id=1,
                content="Will be deleted",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.delete(
            "/messages/delete/del-owned",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"deleted": True}

    def test_delete_returns_404_for_nonexistent_message(self, client, auth_headers):
        """Deleting a message that does not exist should return 404."""
        response = client.delete(
            "/messages/delete/no-such-message",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_returns_404_for_message_owned_by_another_user(
        self, client, auth_headers, db
    ):
        """Deleting a message owned by a different user should return 404."""
        db.add(
            Message(
                message_id="del-other",
                sender_id=99,
                room_id=1,
                content="Someone else's message",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.delete(
            "/messages/delete/del-other",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_returns_404_for_already_deleted_message(
        self, client, auth_headers, db
    ):
        """Trying to delete an already-deleted message should return 404."""
        db.add(
            Message(
                message_id="del-already",
                sender_id=1,
                room_id=1,
                content="[deleted]",
                is_private=False,
                is_deleted=True,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.delete(
            "/messages/delete/del-already",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_requires_auth(self, client):
        """Delete endpoint must require authentication."""
        response = client.delete("/messages/delete/some-id")
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# Reactions endpoint: GET /messages/{message_id}/reactions
# ══════════════════════════════════════════════════════════════════════


class TestReactionsEndpoint:
    """Tests for GET /messages/{message_id}/reactions."""

    def test_returns_empty_list_for_message_with_no_reactions(
        self, client, auth_headers, db
    ):
        """A message with no reactions should return an empty list."""
        db.add(
            Message(
                message_id="react-msg-empty",
                sender_id=1,
                room_id=1,
                content="No reactions here",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.commit()

        response = client.get(
            "/messages/react-msg-empty/reactions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_returns_reactions_for_message(self, client, auth_headers, db):
        """Should return all reactions attached to a message."""
        db.add(
            Message(
                message_id="react-msg-1",
                sender_id=1,
                room_id=1,
                content="React to this",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.add(
            Reaction(
                message_id="react-msg-1",
                user_id=2,
                username="bob",
                emoji="👍",
            )
        )
        db.add(
            Reaction(
                message_id="react-msg-1",
                user_id=3,
                username="carol",
                emoji="❤️",
            )
        )
        db.commit()

        response = client.get(
            "/messages/react-msg-1/reactions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        emojis = {r["emoji"] for r in data}
        assert "👍" in emojis
        assert "❤️" in emojis

    def test_reactions_response_shape(self, client, auth_headers, db):
        """Each reaction in the response should have emoji, username, and user_id."""
        db.add(
            Message(
                message_id="react-shape",
                sender_id=1,
                room_id=1,
                content="Shape test",
                is_private=False,
                sent_at=datetime(2025, 1, 1, 12, 0, 0),
            )
        )
        db.add(
            Reaction(
                message_id="react-shape",
                user_id=5,
                username="testuser",
                emoji="🎉",
            )
        )
        db.commit()

        response = client.get(
            "/messages/react-shape/reactions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        reaction = data[0]
        assert "emoji" in reaction
        assert "username" in reaction
        assert "user_id" in reaction

    def test_reactions_requires_auth(self, client):
        """Reactions endpoint must require authentication."""
        response = client.get("/messages/some-message-id/reactions")
        assert response.status_code == 401

    def test_reactions_returns_empty_for_unknown_message(
        self, client, auth_headers
    ):
        """Requesting reactions for a message that does not exist should return empty list."""
        response = client.get(
            "/messages/nonexistent-msg-id/reactions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []
