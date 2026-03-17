# tests/test_phase2.py
import sys
import os
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from main import app
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD

# Isolated in-memory DB — StaticPool ensures a single shared connection
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

Base.metadata.create_all(bind=test_engine)
with TestSessionLocal() as _db:
    for _name in ["politics", "sports", "movies"]:
        if not _db.query(models.Room).filter(models.Room.name == _name).first():
            _db.add(models.Room(name=_name))
    if not _db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
        _db.add(models.User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_global_admin=True,
        ))
    _db.commit()

# Use a persistent TestClient context so all WS connections share ONE event loop
_client_ctx = TestClient(app).__enter__()


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


def _register_and_login(username: str, password: str = "pass123") -> str:
    _client_ctx.post("/auth/register", json={"username": username, "password": password})
    resp = _client_ctx.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _make_room(name: str) -> int:
    with TestSessionLocal() as db:
        room = models.Room(name=name)
        db.add(room)
        db.commit()
        db.refresh(room)
        return room.id


def _drain_until(ws, expected_type: str) -> dict:
    """Receive and discard messages until one of the expected type arrives."""
    while True:
        msg = ws.receive_json()
        if msg["type"] == expected_type:
            return msg


# ── Test 1: WebSocket connect ─────────────────────────────────────────────────

def test_connect_to_room_via_websocket():
    """First user can connect to a room via WebSocket and receives user_join.
    The server now sends a history frame first, so we drain until user_join."""
    token = _register_and_login("ws_conn_user")
    with _client_ctx.websocket_connect(f"/ws/1?token={token}") as ws:
        data = _drain_until(ws, "user_join")
        assert data["type"] == "user_join"
        assert "ws_conn_user" in data["users"]


# ── Test 2: Send message received by second user ──────────────────────────────

def test_send_message_received_by_second_user():
    """Message sent by user1 is delivered to user2 (and also back to user1).
    Server now broadcasts to ALL users including the sender."""
    token1 = _register_and_login("msg_u1")
    token2 = _register_and_login("msg_u2")
    room_id = _make_room("msg_test_room")

    received_by_u2 = []
    user2_joined = threading.Event()
    message_received = threading.Event()

    def user2_thread():
        with _client_ctx.websocket_connect(f"/ws/{room_id}?token={token2}") as ws2:
            _drain_until(ws2, "user_join")   # skip history, stop at own join
            user2_joined.set()
            msg = _drain_until(ws2, "message")  # skip any system msgs, get the chat msg
            received_by_u2.append(msg)
            message_received.set()

    t2 = threading.Thread(target=user2_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={token1}") as ws1:
        _drain_until(ws1, "user_join")   # skip history, get own join
        t2.start()
        user2_joined.wait(timeout=5)
        _drain_until(ws1, "user_join")   # drain system msgs, get user2's join broadcast
        ws1.send_json({"type": "message", "text": "hello from user1"})
        message_received.wait(timeout=5)

    t2.join(timeout=5)

    assert len(received_by_u2) == 1
    assert received_by_u2[0]["type"] == "message"
    assert received_by_u2[0]["from"] == "msg_u1"
    assert received_by_u2[0]["text"] == "hello from user1"


# ── Test 3: First user in room becomes admin ──────────────────────────────────

def test_first_user_in_room_is_admin():
    """First user to join a fresh room is automatically promoted to room admin.
    Admin row is committed before user_join is broadcast, so the DB check works."""
    token = _register_and_login("first_admin_user")
    room_id = _make_room("admin_test_room")

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={token}") as ws:
        _drain_until(ws, "user_join")  # skip history frame, stop at user_join

        with TestSessionLocal() as db:
            user = db.query(models.User).filter(models.User.username == "first_admin_user").first()
            assert user is not None
            admin_row = db.query(models.RoomAdmin).filter(
                models.RoomAdmin.user_id == user.id,
                models.RoomAdmin.room_id == room_id,
            ).first()
            assert admin_row is not None, "First user should have been promoted to room admin"


# ── Test 4: Admin succession when admin disconnects ───────────────────────────

def test_admin_succession_when_admin_disconnects():
    """When the admin disconnects, the next user in join order becomes room admin."""
    token_admin = _register_and_login("succ_admin_u")
    token_next  = _register_and_login("succ_next_u")
    room_id = _make_room("succession_room")

    new_admin_events = []
    next_user_ready = threading.Event()
    succession_done = threading.Event()

    def next_user_thread():
        with _client_ctx.websocket_connect(f"/ws/{room_id}?token={token_next}") as ws_next:
            _drain_until(ws_next, "user_join")  # skip history, stop at own join
            next_user_ready.set()
            msg = _drain_until(ws_next, "new_admin")  # skip user_left/system, get new_admin
            new_admin_events.append(msg)
            succession_done.set()

    t_next = threading.Thread(target=next_user_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={token_admin}") as ws_admin:
        _drain_until(ws_admin, "user_join")       # skip history, get own join
        t_next.start()
        next_user_ready.wait(timeout=5)
        _drain_until(ws_admin, "user_join")       # drain system msgs, get next user's join

    # ws_admin exits → disconnect → admin succession triggered
    succession_done.wait(timeout=5)
    t_next.join(timeout=5)

    assert len(new_admin_events) == 1
    assert new_admin_events[0]["type"] == "new_admin"
    assert new_admin_events[0]["username"] == "succ_next_u"
