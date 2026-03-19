# tests/test_replay.py — Tests for the message replay API endpoint
import sys
import os
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from auth import hash_password, create_access_token
from main import app

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)

client = TestClient(app)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _use_test_db():
    """Override DB dependency and reset tables between tests."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def db():
    db = TestSessionLocal()
    yield db
    db.close()


@pytest.fixture()
def user_and_token(db):
    """Create a user and return (user, auth_header)."""
    u = models.User(username="replay_user", password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"sub": str(u.id), "username": u.username})
    return u, {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def room(db):
    r = models.Room(name="replay_room")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def seeded_messages(db, room, user_and_token):
    """Seed 5 messages with staggered timestamps."""
    user, _ = user_and_token
    base = datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc)
    msgs = []
    for i in range(5):
        m = models.Message(
            message_id=f"replay-{i}",
            sender_id=user.id,
            room_id=room.id,
            content=f"Message {i}",
            is_private=False,
            sent_at=base + timedelta(minutes=i),
        )
        db.add(m)
        msgs.append(m)
    db.commit()
    return msgs


# ── Tests ─────────────────────────────────────────────────────────────


def test_replay_returns_messages_since(seeded_messages, room, user_and_token):
    """Should return only messages after the 'since' timestamp."""
    _, headers = user_and_token
    # Ask for messages since minute 2 → should get messages 2, 3, 4
    since = "2026-03-19T12:02:00Z"
    resp = client.get(f"/rooms/{room.id}/messages?since={since}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["content"] == "Message 2"
    assert data[2]["content"] == "Message 4"


def test_replay_returns_empty_for_future_since(seeded_messages, room, user_and_token):
    """Should return empty list if since is after all messages."""
    _, headers = user_and_token
    since = "2026-03-19T13:00:00Z"
    resp = client.get(f"/rooms/{room.id}/messages?since={since}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_replay_respects_limit(seeded_messages, room, user_and_token):
    """Should cap results at the requested limit."""
    _, headers = user_and_token
    since = "2026-03-19T12:00:00Z"
    resp = client.get(f"/rooms/{room.id}/messages?since={since}&limit=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_replay_requires_since_param(room, user_and_token):
    """Should 422 if 'since' query param is missing."""
    _, headers = user_and_token
    resp = client.get(f"/rooms/{room.id}/messages", headers=headers)
    assert resp.status_code == 422


def test_replay_404_for_nonexistent_room(user_and_token):
    """Should 404 if room doesn't exist."""
    _, headers = user_and_token
    resp = client.get("/rooms/9999/messages?since=2026-01-01T00:00:00", headers=headers)
    assert resp.status_code == 404


def test_replay_requires_auth(room):
    """Should 401 without an auth token."""
    resp = client.get(f"/rooms/{room.id}/messages?since=2026-01-01T00:00:00")
    assert resp.status_code == 401


def test_replay_excludes_private_messages(db, room, user_and_token):
    """Private messages should not appear in room replay."""
    user, headers = user_and_token
    base = datetime(2026, 3, 19, 14, 0, 0, tzinfo=timezone.utc)

    # Public message
    db.add(models.Message(
        message_id="pub-1", sender_id=user.id, room_id=room.id,
        content="Public", is_private=False, sent_at=base,
    ))
    # Private message (same room_id but is_private=True)
    db.add(models.Message(
        message_id="priv-1", sender_id=user.id, room_id=room.id,
        content="Private", is_private=True, sent_at=base + timedelta(seconds=1),
    ))
    db.commit()

    since = "2026-03-19T14:00:00Z"
    resp = client.get(f"/rooms/{room.id}/messages?since={since}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Public"


def test_replay_includes_message_id(seeded_messages, room, user_and_token):
    """Response should include the message_id field for dedup on the client."""
    _, headers = user_and_token
    since = "2026-03-19T12:00:00Z"
    resp = client.get(f"/rooms/{room.id}/messages?since={since}&limit=1", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["message_id"] == "replay-0"
