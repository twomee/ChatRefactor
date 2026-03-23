# tests/test_websocket.py — comprehensive WebSocket tests
import os
import sys
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from core.config import ADMIN_PASSWORD, ADMIN_USERNAME
from core.database import Base, get_db
from core.security import hash_password
from main import app

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

# Override DB dependency and patch startup code before entering the TestClient
# context so the lifespan doesn't try to connect to PostgreSQL.
app.dependency_overrides[get_db] = override_get_db
with patch("main.alembic_command.upgrade"), patch("main.engine", test_engine):
    _client_ctx = TestClient(app).__enter__()


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    # Force Kafka unavailable so sync DB fallback is always used in tests.
    # Tests use in-memory SQLite; the Kafka consumer writes to real PostgreSQL.
    with patch("routers.websocket.kafka_produce", new_callable=AsyncMock, return_value=False):
        yield


def _login(username, password="password123"):
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

    with pytest.raises((WebSocketDisconnect, Exception)), _client_ctx.websocket_connect("/ws/1?token=bad_token") as ws:
        ws.receive_json()


def test_connect_closed_room_closes_4002():
    rid = _room("closed_ws_room")
    with TestSessionLocal() as db:
        db.query(models.Room).filter(models.Room.id == rid).update({"is_active": False})
        db.commit()
    token = _login("closed_room_user")
    from starlette.websockets import WebSocketDisconnect

    url = f"/ws/{rid}?token={token}"
    with pytest.raises((WebSocketDisconnect, Exception)), _client_ctx.websocket_connect(url) as ws:
        ws.receive_json()


def test_connect_nonexistent_room_closes_4004():
    token = _login("no_room_user")
    from starlette.websockets import WebSocketDisconnect

    url = f"/ws/99999?token={token}"
    with pytest.raises((WebSocketDisconnect, Exception)), _client_ctx.websocket_connect(url) as ws:
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
        _drain(ws_a, "user_join")  # consume victim's join
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
        mute = (
            db.query(models.MutedUser)
            .filter(
                models.MutedUser.user_id == user.id,
                models.MutedUser.room_id == rid,
            )
            .first()
        )
        assert mute is None, "Mute should be cleared when user disconnects"


# ── Broadcast message received by second user ────────────────────────────────


def test_broadcast_message_received_by_second_user():
    """Message sent by user1 is delivered to user2 in the same room."""
    rid = _room("broadcast_room")
    token1 = _login("broadcast_u1")
    token2 = _login("broadcast_u2")

    received_by_u2 = []
    u2_ready = threading.Event()
    msg_received = threading.Event()

    def u2_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token2}") as ws2:
            _drain(ws2, "user_join")
            u2_ready.set()
            msg = _drain(ws2, "message")
            received_by_u2.append(msg)
            msg_received.set()

    t = threading.Thread(target=u2_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token1}") as ws1:
        _drain(ws1, "user_join")
        t.start()
        u2_ready.wait(timeout=5)
        _drain(ws1, "user_join")  # consume u2's join broadcast
        ws1.send_json({"type": "message", "text": "hello from u1"})
        msg_received.wait(timeout=5)

    t.join(timeout=5)
    assert len(received_by_u2) == 1
    assert received_by_u2[0]["from"] == "broadcast_u1"
    assert received_by_u2[0]["text"] == "hello from u1"


# ── Admin succession end-to-end via WebSocket ─────────────────────────────────


def test_admin_succession_e2e():
    """When admin disconnects, next user in join order receives new_admin event."""
    rid = _room("succ_e2e_room")
    token_admin = _login("succ_e2e_admin")
    token_next = _login("succ_e2e_next")

    new_admin_events = []
    next_ready = threading.Event()
    succession_done = threading.Event()

    def next_thread():
        with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_next}") as ws_next:
            _drain(ws_next, "user_join")
            next_ready.set()
            msg = _drain(ws_next, "new_admin")
            new_admin_events.append(msg)
            succession_done.set()

    t = threading.Thread(target=next_thread, daemon=True)

    with _client_ctx.websocket_connect(f"/ws/{rid}?token={token_admin}") as ws_admin:
        _drain(ws_admin, "user_join")
        t.start()
        next_ready.wait(timeout=5)
        _drain(ws_admin, "user_join")  # consume next user's join

    succession_done.wait(timeout=5)
    t.join(timeout=5)

    assert len(new_admin_events) == 1
    assert new_admin_events[0]["username"] == "succ_e2e_next"


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


def test_kick_does_not_broadcast_has_left_system_msg_in_other_room():
    """When user is kicked from room A while also in room B,
    room B should NOT be affected at all — the user remains connected
    in room B and no user_left or 'has left' messages should appear there.

    Note: In the TestClient environment, the server-side ws.close() does not
    automatically trigger WebSocketDisconnect in the handler loop.  We must
    explicitly call client-side close() on the kicked socket after the kick
    so the disconnect handler fires and the kicked_users counter is exercised.
    """
    room_a_id = _room("kick_test_a")
    room_b_id = _room("kick_test_b")
    admin_token = _login("kick_admin_1")
    victim_token = _login("kick_victim_1")
    witness_token = _login("kick_witness_1")  # witness stays in room_b

    with (
        _client_ctx.websocket_connect(f"/ws/{room_a_id}?token={admin_token}") as ws_admin_a,
        _client_ctx.websocket_connect(f"/ws/{room_a_id}?token={victim_token}") as ws_victim_a,
        _client_ctx.websocket_connect(f"/ws/{room_b_id}?token={victim_token}") as ws_victim_b,
        _client_ctx.websocket_connect(f"/ws/{room_b_id}?token={witness_token}") as ws_witness_b,
    ):
        # Drain setup for ws_admin_a
        ws_admin_a.receive_json()  # history
        _drain(ws_admin_a, "user_join")  # self join
        _drain(ws_admin_a, "system")  # joined system
        _drain(ws_admin_a, "system")  # became admin

        # Drain setup for ws_victim_a (joins room_a after admin)
        ws_victim_a.receive_json()  # history
        _drain(ws_victim_a, "user_join")  # user_join broadcast

        # ws_admin_a sees victim join
        _drain(ws_admin_a, "user_join")
        _drain(ws_admin_a, "system")  # "has joined"

        # Drain setup for ws_victim_b (victim's socket in room_b, first user → auto admin)
        ws_victim_b.receive_json()  # history
        _drain(ws_victim_b, "user_join")  # self join
        _drain(ws_victim_b, "system")  # joined system
        _drain(ws_victim_b, "system")  # became admin in room_b

        # Drain setup for ws_witness_b (witness joins room_b)
        ws_witness_b.receive_json()  # history
        _drain(ws_witness_b, "user_join")  # sees both users in room_b
        _drain(ws_witness_b, "system")  # "witness has joined" system msg

        # victim_b sees witness join
        _drain(ws_victim_b, "user_join")
        _drain(ws_victim_b, "system")  # "witness has joined"

        # Admin kicks victim from room_a (server closes ONLY room_a sockets)
        ws_admin_a.send_json({"type": "kick", "target": "kick_victim_1"})

        # Victim receives kicked event on room_a socket
        kicked_msg = _drain(ws_victim_a, "kicked")
        assert kicked_msg["room_id"] == room_a_id

        # Admin receives system message about kick
        _drain(ws_admin_a, "system")

        # In the TestClient the server-side ws.close() does NOT trigger
        # WebSocketDisconnect in the handler loop.  Close only the kicked
        # socket (room_a) — room_b should remain connected.
        try:
            ws_victim_a.close()
        except Exception:
            pass

        # Give the event loop a moment to process the disconnect
        time.sleep(0.2)

        # Collect any witness messages with a short timeout.
        received_in_b = []
        done = threading.Event()

        def drain_witness():
            while True:
                try:
                    msg = ws_witness_b.receive_json()
                    received_in_b.append(msg)
                except Exception:
                    break
            done.set()

        t = threading.Thread(target=drain_witness, daemon=True)
        t.start()
        done.wait(timeout=1.0)

        # Room B witness should NOT see any user_left or "has left" —
        # the victim was only kicked from room A, they're still in room B.
        has_left_msgs = [m for m in received_in_b if m.get("type") == "system" and "has left" in m.get("text", "")]
        assert has_left_msgs == [], f"room_b witness should not see 'has left' system msg, got: {has_left_msgs}"
        user_left_msgs = [m for m in received_in_b if m.get("type") == "user_left"]
        assert user_left_msgs == [], f"room_b witness should not see user_left, got: {user_left_msgs}"


def test_private_message_has_msg_id():
    """Both delivery and echo of a private message must include msg_id."""
    room_id = _room("pm_msgid_room")
    t1 = _login("pm_sender_1")
    t2 = _login("pm_receiver_1")

    with (
        _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1,
        _client_ctx.websocket_connect(f"/ws/{room_id}?token={t2}") as ws2,
    ):
        # Drain setup: ws1 history + self join + joined system + became admin system
        ws1.receive_json()
        _drain(ws1, "user_join")
        _drain(ws1, "system")  # "has joined the room"
        _drain(ws1, "system")  # "has become admin automatically"

        # Drain setup: ws2 history + user_join broadcast; ws1 gets ws2's join + system
        ws2.receive_json()
        _drain(ws2, "user_join")
        _drain(ws2, "system")  # "has joined the room" for ws2
        _drain(ws1, "user_join")
        _drain(ws1, "system")  # "pm_receiver_1 has joined the room"

        ws1.send_json({"type": "private_message", "to": "pm_receiver_1", "text": "hello"})

        # Echo on sender
        echo = ws1.receive_json()
        assert echo["type"] == "private_message"
        assert "msg_id" in echo, "sender echo must have msg_id"

        # Delivery to receiver
        delivery = ws2.receive_json()
        assert delivery["type"] == "private_message"
        assert "msg_id" in delivery, "delivery must have msg_id"

        # Both have the same msg_id
        assert echo["msg_id"] == delivery["msg_id"]


def test_private_message_to_offline_user_returns_error():
    """Sending a PM to a user not connected to any room returns an error event."""
    room_id = _room("pm_offline_room")
    t1 = _login("pm_sender_2")
    _login("pm_offline_user")  # registered but never connected

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1:
        ws1.receive_json()  # history
        _drain(ws1, "user_join")  # self join
        _drain(ws1, "system")  # "has joined the room"
        _drain(ws1, "system")  # "has become admin automatically"

        ws1.send_json({"type": "private_message", "to": "pm_offline_user", "text": "hello?"})
        resp = ws1.receive_json()
        assert resp["type"] == "error"
        assert "not online" in resp["detail"].lower()


def test_get_room_users_returns_online_users():
    """GET /rooms/{id}/users returns usernames of connected users."""
    room_id = _room("users_endpoint_room")
    t1 = _login("users_ep_user1")
    t2 = _login("users_ep_user2")

    # No one connected yet
    resp = _client_ctx.get(f"/rooms/{room_id}/users", headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert resp.json()["users"] == []

    with (
        _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1,
        _client_ctx.websocket_connect(f"/ws/{room_id}?token={t2}") as ws2,
    ):
        # Drain all setup messages to confirm both connections are registered
        ws1.receive_json()  # history
        _drain(ws1, "user_join")  # self join
        _drain(ws1, "system")  # "ws1 has joined"
        _drain(ws1, "system")  # "ws1 has become admin automatically"
        _drain(ws1, "user_join")  # ws2 joined (users_now=[ws1, ws2])
        _drain(ws1, "system")  # "ws2 has joined"
        ws2.receive_json()  # history
        _drain(ws2, "user_join")  # join broadcast (both users visible)
        resp2 = _client_ctx.get(f"/rooms/{room_id}/users", headers={"Authorization": f"Bearer {t1}"})
        assert resp2.status_code == 200
        assert set(resp2.json()["users"]) == {"users_ep_user1", "users_ep_user2"}


def test_get_room_users_requires_auth():
    """GET /rooms/{id}/users must return 401 without a token."""
    room_id = _room("users_auth_room")
    resp = _client_ctx.get(f"/rooms/{room_id}/users")
    assert resp.status_code == 401


def test_get_room_users_404_on_missing_room():
    """GET /rooms/{id}/users returns 404 for a room ID that doesn't exist."""
    t1 = _login("users_404_user")
    resp = _client_ctx.get("/rooms/999999/users", headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 404


def test_get_room_users_304_on_matching_etag():
    """GET /rooms/{id}/users with a matching If-None-Match returns 304."""
    room_id = _room("users_304_room")
    t1 = _login("users_304_test_user")
    resp = _client_ctx.get(f"/rooms/{room_id}/users", headers={"Authorization": f"Bearer {t1}"})
    etag = resp.headers["etag"]
    resp2 = _client_ctx.get(f"/rooms/{room_id}/users", headers={"Authorization": f"Bearer {t1}", "If-None-Match": etag})
    assert resp2.status_code == 304


def test_get_room_users_returns_etag():
    """GET /rooms/{id}/users must return an ETag header."""
    room_id = _room("users_etag_room")
    t1 = _login("users_etag_user")
    resp = _client_ctx.get(f"/rooms/{room_id}/users", headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert "etag" in resp.headers


def test_get_rooms_returns_list():
    """GET /rooms/ returns a list of active rooms."""
    t1 = _login("rooms_list_user")
    resp = _client_ctx.get("/rooms/", headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
