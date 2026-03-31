"""Tests for GET /messages/pm/history/{username}"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest

from app.dal import message_dal
from app.models import UserMessageClear, DeletedPMConversation


def _seed_pm(db, msg_id, sender_id, sender_name, recipient_id, content, sent_at=None):
    message_dal.create_idempotent(
        db,
        message_id=msg_id,
        sender_id=sender_id,
        sender_name=sender_name,
        room_id=None,
        content=content,
        is_private=True,
        recipient_id=recipient_id,
        sent_at=sent_at or datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_returns_messages(mock_lookup, client, db, auth_headers):
    mock_lookup.return_value = {"id": 2, "username": "bob"}
    _seed_pm(db, "pm-h-1", sender_id=1, sender_name="alice", recipient_id=2, content="Hello Bob")
    _seed_pm(db, "pm-h-2", sender_id=2, sender_name="bob", recipient_id=1, content="Hi Alice")

    resp = client.get("/messages/pm/history/bob", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    contents = [m["content"] for m in data]
    assert "Hello Bob" in contents
    assert "Hi Alice" in contents


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_returns_404_when_user_not_found(mock_lookup, client, db, auth_headers):
    mock_lookup.return_value = None
    resp = client.get("/messages/pm/history/nobody", headers=auth_headers)
    assert resp.status_code == 404


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_applies_clear_filter(mock_lookup, client, db, auth_headers):
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t_old = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t_clear = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db, "pm-cl-1", 1, "alice", 2, "Old message", sent_at=t_old)
    _seed_pm(db, "pm-cl-2", 1, "alice", 2, "New message", sent_at=t_new)

    # Insert clear record directly at t_clear — between the two messages
    db.add(UserMessageClear(
        user_id=1, context_type="pm", context_id=2, cleared_at=t_clear,
    ))
    db.commit()

    resp = client.get("/messages/pm/history/bob", headers=auth_headers)
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()]
    assert "Old message" not in contents
    assert "New message" in contents


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_applies_deletion_filter(mock_lookup, client, db, auth_headers):
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t_old = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t_delete = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db, "pm-dl-1", 1, "alice", 2, "Before delete", sent_at=t_old)
    _seed_pm(db, "pm-dl-2", 1, "alice", 2, "After delete", sent_at=t_new)

    # Insert deletion record directly at t_delete — between the two messages
    db.add(DeletedPMConversation(
        user_id=1, other_user_id=2, deleted_at=t_delete,
    ))
    db.commit()

    resp = client.get("/messages/pm/history/bob", headers=auth_headers)
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()]
    assert "Before delete" not in contents
    assert "After delete" in contents


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_requires_auth(mock_lookup, client, db):
    mock_lookup.return_value = {"id": 2, "username": "bob"}
    resp = client.get("/messages/pm/history/bob")
    assert resp.status_code == 401


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_pagination_before(mock_lookup, client, db, auth_headers):
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db, "pm-pg-1", 1, "alice", 2, "Early", sent_at=t1)
    _seed_pm(db, "pm-pg-2", 1, "alice", 2, "Late", sent_at=t2)

    resp = client.get(
        f"/messages/pm/history/bob?before={quote(t2.isoformat())}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Early"
