# tests/test_clear_and_pm_deletion.py — Tests for clear history, context endpoints,
#                                       and PM conversation deletion
#
# Covers:
#   - POST /messages/clear (clear history)
#   - GET /messages/rooms/{room_id}/history (filtered by clear)
#   - GET /messages/rooms/{room_id}?since=... (filtered by clear)
#   - GET /messages/rooms/{room_id}/context (scroll-to-message)
#   - GET /messages/pm/context (PM scroll-to-message)
#   - POST /messages/pm/delete-conversation
#   - GET /messages/pm/deleted-conversations
#   - DAL unit tests for clear_dal and pm_deletion_dal
#   - Edge cases: idempotent clears, non-existent contexts, auth required
from datetime import datetime, timedelta, timezone

import pytest

from app.dal import clear_dal, pm_deletion_dal
from app.models import Message


# ══════════════════════════════════════════════════════════════════════
# DAL Unit Tests — clear_dal
# ══════════════════════════════════════════════════════════════════════


class TestClearDAL:
    """Unit tests for app/dal/clear_dal.py."""

    def test_upsert_clear_creates_new_record(self, db):
        """First clear for a context should create a new record."""
        record = clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        assert record.user_id == 1
        assert record.context_type == "room"
        assert record.context_id == 10
        assert record.cleared_at is not None

    def test_upsert_clear_updates_existing_record(self, db):
        """Re-clearing the same context should update cleared_at, not create a duplicate."""
        first = clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        first_time = first.cleared_at

        second = clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        assert second.id == first.id  # same record
        assert second.cleared_at >= first_time  # timestamp updated

    def test_get_clear_returns_timestamp(self, db):
        """get_clear should return cleared_at when a clear record exists."""
        clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        result = clear_dal.get_clear(db, user_id=1, context_type="room", context_id=10)
        assert result is not None
        assert isinstance(result, datetime)

    def test_get_clear_returns_none_when_not_cleared(self, db):
        """get_clear should return None when no clear record exists."""
        result = clear_dal.get_clear(db, user_id=99, context_type="room", context_id=99)
        assert result is None

    def test_different_contexts_are_independent(self, db):
        """Clearing room 10 should not affect room 20."""
        clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        assert clear_dal.get_clear(db, user_id=1, context_type="room", context_id=10) is not None
        assert clear_dal.get_clear(db, user_id=1, context_type="room", context_id=20) is None

    def test_different_users_are_independent(self, db):
        """User 1 clearing a room should not affect user 2."""
        clear_dal.upsert_clear(db, user_id=1, context_type="room", context_id=10)
        assert clear_dal.get_clear(db, user_id=1, context_type="room", context_id=10) is not None
        assert clear_dal.get_clear(db, user_id=2, context_type="room", context_id=10) is None

    def test_pm_context_type(self, db):
        """Clear should work for 'pm' context_type as well."""
        clear_dal.upsert_clear(db, user_id=1, context_type="pm", context_id=2)
        result = clear_dal.get_clear(db, user_id=1, context_type="pm", context_id=2)
        assert result is not None


# ══════════════════════════════════════════════════════════════════════
# DAL Unit Tests — pm_deletion_dal
# ══════════════════════════════════════════════════════════════════════


class TestPMDeletionDAL:
    """Unit tests for app/dal/pm_deletion_dal.py."""

    def test_delete_conversation_creates_record(self, db):
        """Deleting a PM conversation should create a deletion record."""
        record = pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        assert record.user_id == 1
        assert record.other_user_id == 2
        assert record.deleted_at is not None

    def test_delete_conversation_is_idempotent(self, db):
        """Re-deleting the same conversation should update, not duplicate."""
        first = pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        first_time = first.deleted_at

        second = pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        assert second.id == first.id
        assert second.deleted_at >= first_time

    def test_get_deleted_conversations_returns_list(self, db):
        """Should return all deleted conversations for a user."""
        pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=3)

        result = pm_deletion_dal.get_deleted_conversations(db, user_id=1)
        assert len(result) == 2
        other_ids = {r["other_user_id"] for r in result}
        assert other_ids == {2, 3}

    def test_get_deleted_conversations_empty(self, db):
        """Should return empty list when no conversations deleted."""
        result = pm_deletion_dal.get_deleted_conversations(db, user_id=99)
        assert result == []

    def test_remove_deletion_removes_record(self, db):
        """remove_deletion should remove the deletion record."""
        pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        assert pm_deletion_dal.remove_deletion(db, user_id=1, other_user_id=2) is True

        result = pm_deletion_dal.get_deleted_conversations(db, user_id=1)
        assert len(result) == 0

    def test_remove_deletion_returns_false_when_not_found(self, db):
        """remove_deletion should return False when record does not exist."""
        assert pm_deletion_dal.remove_deletion(db, user_id=99, other_user_id=99) is False

    def test_deletion_is_per_user(self, db):
        """User 1 deleting conversation with user 2 should not affect user 2's view."""
        pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)

        user1_deleted = pm_deletion_dal.get_deleted_conversations(db, user_id=1)
        user2_deleted = pm_deletion_dal.get_deleted_conversations(db, user_id=2)

        assert len(user1_deleted) == 1
        assert len(user2_deleted) == 0

    def test_get_pm_deletion_timestamp_returns_none_when_not_deleted(self, db):
        """get_pm_deletion_timestamp should return None when no deletion record exists."""
        result = pm_deletion_dal.get_pm_deletion_timestamp(db, user_id=1, other_user_id=2)
        assert result is None

    def test_get_pm_deletion_timestamp_returns_datetime_after_deletion(self, db):
        """get_pm_deletion_timestamp should return the deleted_at datetime after deletion."""
        pm_deletion_dal.delete_conversation(db, user_id=1, other_user_id=2)
        result = pm_deletion_dal.get_pm_deletion_timestamp(db, user_id=1, other_user_id=2)
        assert result is not None
        from datetime import datetime
        assert isinstance(result, datetime)


# ══════════════════════════════════════════════════════════════════════
# REST API — Clear history endpoint: POST /messages/clear
# ══════════════════════════════════════════════════════════════════════


class TestClearHistoryEndpoint:
    """Tests for POST /messages/clear."""

    def test_clear_room_returns_200(self, client, auth_headers):
        """Clearing room history should return 200."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "room", "context_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {"detail": "History cleared"}

    def test_clear_pm_returns_200(self, client, auth_headers):
        """Clearing PM history should return 200."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "pm", "context_id": 2},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {"detail": "History cleared"}

    def test_clear_invalid_context_type_returns_422(self, client, auth_headers):
        """Invalid context_type should return 422 validation error."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "invalid", "context_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_clear_idempotent(self, client, auth_headers):
        """Clearing the same context twice should succeed both times."""
        for _ in range(2):
            response = client.post(
                "/messages/clear",
                json={"context_type": "room", "context_id": 1},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_clear_requires_auth(self, client):
        """Clear endpoint must require authentication."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "room", "context_id": 1},
        )
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# History filtering after clear
# ══════════════════════════════════════════════════════════════════════


class TestHistoryFilteringAfterClear:
    """Tests that room history respects per-user clear markers."""

    def test_history_excludes_cleared_messages(
        self, client, auth_headers, sample_messages, db
    ):
        """After clearing, messages before cleared_at should be excluded."""
        # Sample messages are at 12:00, 12:01, 12:02, 12:03, 12:04
        # Clear at 12:02 — should exclude messages at 12:00, 12:01, 12:02
        from app.models import UserMessageClear

        db.add(
            UserMessageClear(
                user_id=1,
                context_type="room",
                context_id=1,
                cleared_at=datetime(2025, 1, 1, 12, 2, 0),
            )
        )
        db.commit()

        response = client.get("/messages/rooms/1/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Only messages at 12:03 and 12:04 should remain
        assert len(data) == 2
        assert data[0]["content"] == "Test message 3"
        assert data[1]["content"] == "Test message 4"

    def test_replay_excludes_cleared_messages(
        self, client, auth_headers, sample_messages, db
    ):
        """Replay endpoint should also filter cleared messages."""
        from app.models import UserMessageClear

        db.add(
            UserMessageClear(
                user_id=1,
                context_type="room",
                context_id=1,
                cleared_at=datetime(2025, 1, 1, 12, 2, 0),
            )
        )
        db.commit()

        since = "2025-01-01T12:00:00"
        response = client.get(
            f"/messages/rooms/1?since={since}&limit=100", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Messages at 12:00, 12:01, 12:02 excluded; 12:03, 12:04 remain
        assert len(data) == 2

    def test_history_unaffected_without_clear(
        self, client, auth_headers, sample_messages
    ):
        """Without a clear marker, all messages should be returned."""
        response = client.get("/messages/rooms/1/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_clear_does_not_affect_other_users(
        self, client, auth_headers, auth_headers_user2, sample_messages, db
    ):
        """User 1 clearing room should not affect user 2's history."""
        from app.models import UserMessageClear

        # Messages are at 12:00, 12:01, 12:02, 12:03, 12:04
        # Clear at 12:03:30 — only msg at 12:04 survives (sent_at > cleared_at)
        db.add(
            UserMessageClear(
                user_id=1,
                context_type="room",
                context_id=1,
                cleared_at=datetime(2025, 1, 1, 12, 3, 30),
            )
        )
        db.commit()

        # User 1 should see only 1 message (12:04)
        resp1 = client.get("/messages/rooms/1/history", headers=auth_headers)
        assert len(resp1.json()) == 1
        assert resp1.json()[0]["content"] == "Test message 4"

        # User 2 should see all 5 messages (no clear for them)
        resp2 = client.get("/messages/rooms/1/history", headers=auth_headers_user2)
        assert len(resp2.json()) == 5


# ══════════════════════════════════════════════════════════════════════
# Context endpoints: GET /messages/rooms/{room_id}/context
# ══════════════════════════════════════════════════════════════════════


class TestRoomContextEndpoint:
    """Tests for GET /messages/rooms/{room_id}/context."""

    def test_context_returns_messages_around_target(
        self, client, auth_headers, sample_messages
    ):
        """Should return messages before and after the target message."""
        # Target: msg-002 (12:02), before=2, after=2
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-002&before=2&after=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have msg-000, msg-001, msg-002, msg-003, msg-004
        assert len(data) == 5
        message_ids = [m["message_id"] for m in data]
        assert message_ids == ["msg-000", "msg-001", "msg-002", "msg-003", "msg-004"]

    def test_context_with_limited_before(self, client, auth_headers, sample_messages):
        """Should respect the before parameter."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-002&before=1&after=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        message_ids = [m["message_id"] for m in data]
        assert message_ids == ["msg-001", "msg-002", "msg-003"]

    def test_context_first_message(self, client, auth_headers, sample_messages):
        """First message should have no before messages."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-000&before=5&after=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # msg-000, msg-001, msg-002
        assert len(data) == 3
        assert data[0]["message_id"] == "msg-000"

    def test_context_last_message(self, client, auth_headers, sample_messages):
        """Last message should have no after messages."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-004&before=2&after=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # msg-002, msg-003, msg-004
        assert len(data) == 3
        assert data[-1]["message_id"] == "msg-004"

    def test_context_nonexistent_message_returns_404(
        self, client, auth_headers, sample_messages
    ):
        """Should return 404 for a message that does not exist in the room."""
        response = client.get(
            "/messages/rooms/1/context?message_id=does-not-exist&before=2&after=2",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_context_wrong_room_returns_404(
        self, client, auth_headers, sample_messages
    ):
        """Should return 404 when message exists in a different room."""
        response = client.get(
            "/messages/rooms/999/context?message_id=msg-002&before=2&after=2",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_context_requires_auth(self, client):
        """Context endpoint must require authentication."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-002&before=2&after=2"
        )
        assert response.status_code == 401

    def test_context_response_shape(self, client, auth_headers, sample_messages):
        """Each message in context response should have expected fields."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-002&before=0&after=0",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        msg = data[0]
        assert "message_id" in msg
        assert "sender_id" in msg
        assert "content" in msg
        assert "room_id" in msg
        assert "sent_at" in msg


# ══════════════════════════════════════════════════════════════════════
# PM Context endpoint: GET /messages/pm/context
# ══════════════════════════════════════════════════════════════════════


class TestPMContextEndpoint:
    """Tests for GET /messages/pm/context."""

    def test_pm_context_returns_messages_around_target(
        self, client, auth_headers, sample_pm_messages
    ):
        """Should return PM messages before and after the target."""
        # Target: pm-002 (14:02)
        response = client.get(
            "/messages/pm/context?message_id=pm-002&before=2&after=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        message_ids = [m["message_id"] for m in data]
        assert message_ids == ["pm-000", "pm-001", "pm-002", "pm-003", "pm-004"]

    def test_pm_context_with_limited_window(
        self, client, auth_headers, sample_pm_messages
    ):
        """Should respect before/after parameters."""
        response = client.get(
            "/messages/pm/context?message_id=pm-002&before=1&after=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        message_ids = [m["message_id"] for m in data]
        assert message_ids == ["pm-001", "pm-002", "pm-003"]

    def test_pm_context_nonexistent_message_returns_404(
        self, client, auth_headers
    ):
        """Should return 404 for a PM message that does not exist."""
        response = client.get(
            "/messages/pm/context?message_id=does-not-exist",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_pm_context_requires_auth(self, client):
        """PM context endpoint must require authentication."""
        response = client.get("/messages/pm/context?message_id=pm-002")
        assert response.status_code == 401

    def test_pm_context_response_shape(
        self, client, auth_headers, sample_pm_messages
    ):
        """Each PM message should have expected fields."""
        response = client.get(
            "/messages/pm/context?message_id=pm-002&before=0&after=0",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        msg = data[0]
        assert "message_id" in msg
        assert "sender_id" in msg
        assert "content" in msg
        assert "recipient_id" in msg
        assert "sent_at" in msg


# ══════════════════════════════════════════════════════════════════════
# PM Deletion endpoints
# ══════════════════════════════════════════════════════════════════════


class TestDeletePMConversationEndpoint:
    """Tests for POST /messages/pm/delete-conversation."""

    def test_delete_pm_conversation_returns_200(self, client, auth_headers):
        """Deleting a PM conversation should return 200."""
        response = client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 2},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {"detail": "Conversation deleted"}

    def test_delete_pm_conversation_idempotent(self, client, auth_headers):
        """Re-deleting the same PM conversation should succeed."""
        for _ in range(2):
            response = client.post(
                "/messages/pm/delete-conversation",
                json={"other_user_id": 2},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_delete_pm_conversation_requires_auth(self, client):
        """PM deletion endpoint must require authentication."""
        response = client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 2},
        )
        assert response.status_code == 401


class TestGetDeletedPMConversationsEndpoint:
    """Tests for GET /messages/pm/deleted-conversations."""

    def test_returns_empty_when_no_deletions(self, client, auth_headers):
        """Should return empty list when no PM conversations deleted."""
        response = client.get(
            "/messages/pm/deleted-conversations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_deleted_conversations(self, client, auth_headers):
        """Should return list of deleted PM conversations."""
        # Delete two conversations
        client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 2},
            headers=auth_headers,
        )
        client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 3},
            headers=auth_headers,
        )

        response = client.get(
            "/messages/pm/deleted-conversations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        other_ids = {d["other_user_id"] for d in data}
        assert other_ids == {2, 3}

    def test_deleted_conversations_response_shape(self, client, auth_headers):
        """Each deleted conversation should have other_user_id and deleted_at."""
        client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 5},
            headers=auth_headers,
        )

        response = client.get(
            "/messages/pm/deleted-conversations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "other_user_id" in data[0]
        assert "deleted_at" in data[0]

    def test_deleted_conversations_requires_auth(self, client):
        """Deleted conversations endpoint must require authentication."""
        response = client.get("/messages/pm/deleted-conversations")
        assert response.status_code == 401

    def test_deletion_is_per_user(self, client, auth_headers, auth_headers_user2):
        """User 1's deletions should not appear for user 2."""
        client.post(
            "/messages/pm/delete-conversation",
            json={"other_user_id": 3},
            headers=auth_headers,
        )

        resp1 = client.get(
            "/messages/pm/deleted-conversations", headers=auth_headers
        )
        resp2 = client.get(
            "/messages/pm/deleted-conversations", headers=auth_headers_user2
        )

        assert len(resp1.json()) == 1
        assert len(resp2.json()) == 0


# ══════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests for clear and PM deletion features."""

    def test_clear_nonexistent_room_succeeds(self, client, auth_headers):
        """Clearing a room that has no messages should succeed (no-op)."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "room", "context_id": 99999},
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_clear_missing_context_type_returns_422(self, client, auth_headers):
        """Missing context_type should return 422."""
        response = client.post(
            "/messages/clear",
            json={"context_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_clear_missing_context_id_returns_422(self, client, auth_headers):
        """Missing context_id should return 422."""
        response = client.post(
            "/messages/clear",
            json={"context_type": "room"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_delete_pm_missing_other_user_id_returns_422(self, client, auth_headers):
        """Missing other_user_id should return 422."""
        response = client.post(
            "/messages/pm/delete-conversation",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_context_with_zero_before_and_after(
        self, client, auth_headers, sample_messages
    ):
        """before=0 and after=0 should return just the target message."""
        response = client.get(
            "/messages/rooms/1/context?message_id=msg-002&before=0&after=0",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["message_id"] == "msg-002"

    def test_history_after_clearing_all_messages(
        self, client, auth_headers, sample_messages, db
    ):
        """Clearing at a time after all messages should return empty history."""
        from app.models import UserMessageClear

        db.add(
            UserMessageClear(
                user_id=1,
                context_type="room",
                context_id=1,
                cleared_at=datetime(2026, 1, 1, 0, 0, 0),  # far future
            )
        )
        db.commit()

        response = client.get("/messages/rooms/1/history", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []
