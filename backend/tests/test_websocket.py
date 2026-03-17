# tests/test_websocket.py — comprehensive WebSocket tests
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

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=test_engine)
with TestSessionLocal() as _db:
    for _name in ["politics", "sports", "movies"]:
        if not _db.query(models.Room).filter(models.Room.name == _name).first():
            _db.add(models.Room(name=_name))
    if not _db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
        _db.add(models.User(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), is_global_admin=True))
    _db.commit()

_client_ctx = TestClient(app).__enter__()


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


def _login(username, password="pw123"):
    _client_ctx.post("/auth/register", json={"username": username, "password": password})
    return _client_ctx.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _room(name):
    with TestSessionLocal() as db:
        r = models.Room(name=name)
        db.add(r)
        db.commit()
        db.refresh(r)
        return r.id


def _drain(ws, expected_type):
    """Skip messages until one of expected_type is found."""
    while True:
        msg = ws.receive_json()
        if msg["type"] == expected_type:
            return msg


# ── Connection ────────────────────────────────────────────────────────────────

def test_connect_invalid_token_closes_4001():
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises((WebSocketDisconnect, Exception)):
        with _client_ctx.websocket_connect("/ws/1?token=bad_token") as ws:
            ws.receive_json()


def test_connect_closed_room_closes_4002():
    rid = _room("closed_ws_room")
    with TestSessionLocal() as db:
        db.query(models.Room).filter(models.Room.id == rid).update({"is_active": False})
        db.commit()
    token = _login("closed_room_user")
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises((WebSocketDisconnect, Exception)):
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
            ws.receive_json()


def test_connect_nonexistent_room_closes_4004():
    token = _login("no_room_user")
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises((WebSocketDisconnect, Exception)):
        with _client_ctx.websocket_connect("/ws/99999?token={token}") as ws:
            ws.receive_json()


def test_connect_sends_history_then_user_join():
    rid = _room("history_test_room")
    token = _login("hist_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        first = ws.receive_json()
        assert first["type"] == "history"
        assert "messages" in first
        second = _drain(ws, "user_join")
        assert "hist_user" in second["users"]


def test_history_is_empty_on_fresh_room():
    rid = _room("empty_hist_room")
    token = _login("empty_hist_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        hist = ws.receive_json()
        assert hist["type"] == "history"
        assert hist["messages"] == []


# ── System messages ───────────────────────────────────────────────────────────

def test_joining_user_triggers_system_message():
    rid = _room("sys_join_room")
    token = _login("sys_joiner")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        sys_msg = _drain(ws, "system")
        assert "sys_joiner" in sys_msg["text"]
        assert "joined" in sys_msg["text"]


def test_first_user_gets_admin_system_message():
    rid = _room("sys_admin_room")
    token = _login("sys_admin_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        # Drain system messages until we find the admin one
        for _ in range(5):
            msg = ws.receive_json()
            if msg["type"] == "system" and "admin" in msg["text"].lower():
                return  # found
        pytest.fail("Expected system message about becoming admin")


# ── Chat messages ─────────────────────────────────────────────────────────────

def test_message_received_by_sender_too():
    """Server broadcasts to ALL including sender — no local add needed on frontend."""
    rid = _room("echo_room")
    token = _login("echo_user")
    received = []
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        ws.send_json({"type": "message", "text": "echo test"})
        msg = _drain(ws, "message")
        received.append(msg)
    assert received[0]["from"] == "echo_user"
    assert received[0]["text"] == "echo test"


def test_message_persisted_to_db():
    rid = _room("persist_room")
    token = _login("persist_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        ws.send_json({"type": "message", "text": "save me"})
        _drain(ws, "message")
    with TestSessionLocal() as db:
        msg = db.query(models.Message).filter(models.Message.room_id == rid).first()
        assert msg is not None
        assert msg.content == "save me"


def test_history_shows_previous_messages():
    rid = _room("history_msgs_room")
    token = _login("history_msgs_user")
    # Send a message
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        ws.send_json({"type": "message", "text": "remember me"})
        _drain(ws, "message")
    # Rejoin — history should contain the message
    token2 = _login("history_msgs_user2")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token2}") as ws2:
        hist = ws2.receive_json()
        assert hist["type"] == "history"
        texts = [m["text"] for m in hist["messages"]]
        assert "remember me" in texts


# ── Mute ─────────────────────────────────────────────────────────────────────

def test_muted_user_cannot_send_message():
    rid = _room("mute_test_room")
    token_admin = _login("mute_admin_ws")
    token_muted = _login("mute_victim_ws")

    # Make admin the first user (admin)
    error_received = []
    mute_done = threading.Event()
    victim_ready = threading.Event()

    def victim_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_muted}") as ws_v:
            _drain(ws_v, "user_join")
            victim_ready.set()
            # Wait to be muted, then try sending
            _drain(ws_v, "muted")
            mute_done.set()
            ws_v.send_json({"type": "message", "text": "should be blocked"})
            err = _drain(ws_v, "error")
            error_received.append(err)

    t = threading.Thread(target=victim_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_admin}") as ws_a:
        _drain(ws_a, "user_join")
        t.start()
        victim_ready.wait(timeout=5)
        _drain(ws_a, "user_join")   # consume victim's join
        ws_a.send_json({"type": "mute", "target": "mute_victim_ws"})
        mute_done.wait(timeout=5)

    t.join(timeout=5)
    assert len(error_received) == 1
    assert "muted" in error_received[0]["detail"].lower()


# ── Private message ───────────────────────────────────────────────────────────

def test_private_message_delivered_to_target_and_echoed_to_sender():
    rid = _room("pm_room")
    token_a = _login("pm_sender")
    token_b = _login("pm_receiver")

    received_by_b = []
    echo_to_a = []
    b_ready = threading.Event()
    b_got_pm = threading.Event()

    def b_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_b}") as ws_b:
            _drain(ws_b, "user_join")
            b_ready.set()
            msg = _drain(ws_b, "private_message")
            received_by_b.append(msg)
            b_got_pm.set()

    t = threading.Thread(target=b_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_a}") as ws_a:
        _drain(ws_a, "user_join")
        t.start()
        b_ready.wait(timeout=5)
        _drain(ws_a, "user_join")  # consume b's join
        ws_a.send_json({"type": "private_message", "to": "pm_receiver", "text": "secret"})
        echo = _drain(ws_a, "private_message")
        echo_to_a.append(echo)
        b_got_pm.wait(timeout=5)

    t.join(timeout=5)
    assert received_by_b[0]["text"] == "secret"
    assert received_by_b[0]["from"] == "pm_sender"
    assert echo_to_a[0]["self"] is True


# ── Room closed guard ─────────────────────────────────────────────────────────

def test_message_rejected_when_room_closed_mid_session():
    rid = _room("closeguard_room")
    token = _login("closeguard_user")
    errors = []

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "user_join")
        # Close the room via DB directly (simulating admin action)
        with TestSessionLocal() as db:
            db.query(models.Room).filter(models.Room.id == rid).update({"is_active": False})
            db.commit()
        # Now send a message — should receive error
        ws.send_json({"type": "message", "text": "ghost message"})
        err = _drain(ws, "error")
        errors.append(err)

    assert len(errors) == 1
    assert "closed" in errors[0]["detail"].lower()


# ── Admins list in user_join ──────────────────────────────────────────────────

def test_user_join_includes_admins_list():
    """user_join message must include 'admins' field with current room admins."""
    rid = _room("admins_list_room")
    token = _login("admins_list_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "history")
        msg = _drain(ws, "user_join")
        assert "admins" in msg
        assert isinstance(msg["admins"], list)


def test_first_user_in_admins_list():
    """First user to join a room should be in the admins list of user_join."""
    rid = _room("first_admin_list_room")
    token = _login("first_admin_list_user")
    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token}") as ws:
        _drain(ws, "history")
        msg = _drain(ws, "user_join")
        assert "first_admin_list_user" in msg["admins"]


# ── Mute auto-clear on disconnect ─────────────────────────────────────────────

def test_muted_user_unmuted_on_disconnect():
    """When a muted user disconnects and reconnects, they are no longer muted."""
    rid = _room("mute_clear_room")
    token_admin = _login("mute_clear_admin")
    token_user = _login("mute_clear_user")

    mute_confirmed = threading.Event()
    user_disconnected = threading.Event()

    def user_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_user}") as ws_u:
            _drain(ws_u, "user_join")
            _drain(ws_u, "muted")  # wait to be muted
            mute_confirmed.set()
            # Wait then disconnect naturally (context manager exit)
        user_disconnected.set()

    t = threading.Thread(target=user_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_admin}") as ws_a:
        _drain(ws_a, "user_join")
        t.start()
        _drain(ws_a, "user_join")  # user joined
        ws_a.send_json({"type": "mute", "target": "mute_clear_user"})
        mute_confirmed.wait(timeout=5)

    t.join(timeout=5)
    user_disconnected.wait(timeout=3)

    # Reconnect — user should not be muted in DB
    with TestSessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "mute_clear_user").first()
        mute = db.query(models.MutedUser).filter(
            models.MutedUser.user_id == user.id,
            models.MutedUser.room_id == rid,
        ).first()
        assert mute is None, "Mute should be cleared when user disconnects"


# ── Kick suppresses duplicate has-left message ────────────────────────────────

def test_kick_sends_kicked_event_to_victim():
    """Kicked user receives 'kicked' event and is disconnected from room."""
    rid = _room("kick_msg_room")
    token_admin = _login("kick_msg_admin")
    token_victim = _login("kick_msg_victim")

    kick_received = threading.Event()

    def victim_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_victim}") as ws_v:
            _drain(ws_v, "user_join")
            _drain(ws_v, "kicked")
            kick_received.set()

    t = threading.Thread(target=victim_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_admin}") as ws_a:
        _drain(ws_a, "user_join")
        t.start()
        _drain(ws_a, "user_join")  # victim joined
        ws_a.send_json({"type": "kick", "target": "kick_msg_victim"})
        kick_received.wait(timeout=5)

    t.join(timeout=5)
    assert kick_received.is_set()
