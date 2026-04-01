"""Chat WebSocket tests — messaging, typing, edit, delete, reactions, refresh behavior."""

import asyncio
import json
import time

import pytest
import websockets

from conftest import auth_header


async def ws_connect(ws_url: str, path: str, token: str, silent: bool = False):
    """Connect to a WebSocket endpoint. Returns the connection."""
    url = f"{ws_url}{path}?token={token}"
    if silent:
        url += "&silent=1"
    return await websockets.connect(url, ping_interval=None, open_timeout=10)


async def recv_until(ws, msg_type: str, timeout: float = 5.0):
    """Receive messages until one matches the given type, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = deadline - time.time()
            raw = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
            data = json.loads(raw)
            if data.get("type") == msg_type:
                return data
        except asyncio.TimeoutError:
            break
    return None


async def drain(ws, timeout: float = 0.5):
    """Drain all pending messages from a WebSocket."""
    messages = []
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            messages.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
    return messages


class TestWebSocketConnection:
    """Basic WebSocket connectivity."""

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_connect_to_lobby(self, ws_url: str, user1: dict):
        ws = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        assert ws.open
        await ws.close()

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_connect_to_room(self, ws_url: str, user1: dict, test_room: dict):
        lobby = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        msg = await recv_until(room, "history", timeout=5)
        assert room.open
        await room.close()
        await lobby.close()


class TestRoomMessaging:
    """Sending messages, typing, edit, delete, reactions in a room."""

    @pytest.mark.asyncio
    async def test_send_message_broadcast(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.send(json.dumps({"type": "message", "text": "hello from e2e"}))

        msg = await recv_until(room2, "message", timeout=5)
        assert msg is not None, "User2 did not receive message broadcast"
        assert msg["text"] == "hello from e2e"
        assert msg["from"] == user1["username"]
        assert "msg_id" in msg

        await room1.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_typing_indicator_not_echoed(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.send(json.dumps({"type": "typing"}))

        msg = await recv_until(room2, "typing", timeout=3)
        assert msg is not None, "User2 did not receive typing indicator"
        assert msg["username"] == user1["username"]

        own_msgs = await drain(room1, timeout=1)
        typing_echo = [m for m in own_msgs if m.get("type") == "typing"]
        assert len(typing_echo) == 0, "Sender received their own typing indicator"

        await room1.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_edit_message(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.send(json.dumps({"type": "message", "text": "original text"}))
        msg = await recv_until(room2, "message", timeout=5)
        msg_id = msg["msg_id"]

        await room1.send(json.dumps({
            "type": "edit_message", "msg_id": msg_id, "text": "edited text"
        }))

        edit_msg = await recv_until(room2, "message_edited", timeout=5)
        assert edit_msg is not None, "User2 did not receive edit broadcast"
        assert edit_msg["msg_id"] == msg_id
        assert edit_msg["text"] == "edited text"

        await room1.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_delete_message(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.send(json.dumps({"type": "message", "text": "delete me"}))
        msg = await recv_until(room2, "message", timeout=5)
        msg_id = msg["msg_id"]

        await room1.send(json.dumps({"type": "delete_message", "msg_id": msg_id}))

        del_msg = await recv_until(room2, "message_deleted", timeout=5)
        assert del_msg is not None, "User2 did not receive delete broadcast"
        assert del_msg["msg_id"] == msg_id

        await room1.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_add_and_remove_reaction(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.send(json.dumps({"type": "message", "text": "react to me"}))
        msg = await recv_until(room2, "message", timeout=5)
        msg_id = msg["msg_id"]

        await room2.send(json.dumps({
            "type": "add_reaction", "msg_id": msg_id, "emoji": "👍"
        }))
        reaction = await recv_until(room1, "reaction_added", timeout=5)
        assert reaction is not None, "Did not receive reaction_added"
        assert reaction["emoji"] == "👍"
        assert reaction["username"] == user2["username"]

        await room2.send(json.dumps({
            "type": "remove_reaction", "msg_id": msg_id, "emoji": "👍"
        }))
        removed = await recv_until(room1, "reaction_removed", timeout=5)
        assert removed is not None, "Did not receive reaction_removed"
        assert removed["emoji"] == "👍"

        await room1.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_clear_room_history(self, api, kong_url: str, ws_url: str, user1: dict, test_room: dict):
        lobby = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room)
        await room.send(json.dumps({"type": "message", "text": "history test msg"}))
        await drain(room, timeout=2)
        await room.close()
        await lobby.close()

        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}/history?limit=50",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert len(resp.json()) > 0

        resp = api.post(
            f"{kong_url}/messages/clear",
            json={"context_type": "room", "context_id": test_room["id"]},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}/history?limit=50",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestRefreshBehavior:
    """Verify that browser refresh (disconnect + reconnect) behaves correctly."""

    @pytest.mark.asyncio
    async def test_refresh_no_leave_join_broadcast(self, ws_url: str, user1: dict, user2: dict, test_room: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room1)

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{test_room['id']}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.close()
        await asyncio.sleep(0.5)

        room1_new = await ws_connect(
            ws_url, f"/ws/{test_room['id']}", user1["token"], silent=True
        )

        msgs = await drain(room2, timeout=2)
        leave_join = [
            m for m in msgs
            if m.get("type") in ("user_left", "user_join")
            and m.get("username") == user1["username"]
            and not m.get("silent", False)
        ]
        assert len(leave_join) == 0, f"User2 received unexpected leave/join broadcasts: {leave_join}"

        await room1_new.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_refresh_admin_role_preserved(
        self, ws_url: str, api, kong_url: str, admin_token: str, user1: dict, user2: dict, timestamp: str
    ):
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"adminrefresh_{timestamp}"},
            headers=auth_header(admin_token),
        )
        room_id = resp.json()["id"]

        api.post(
            f"{kong_url}/rooms/{room_id}/admins",
            json={"user_id": user1["user_id"]},
            headers=auth_header(admin_token),
        )

        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room1 = await ws_connect(ws_url, f"/ws/{room_id}", user1["token"])
        join_msg = await recv_until(room1, "user_join", timeout=5)
        assert user1["username"] in join_msg.get("admins", [])

        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        room2 = await ws_connect(ws_url, f"/ws/{room_id}", user2["token"])
        await drain(room2)
        await drain(room1)

        await room1.close()
        await asyncio.sleep(0.5)
        room1_new = await ws_connect(
            ws_url, f"/ws/{room_id}", user1["token"], silent=True
        )
        join_msg = await recv_until(room1_new, "user_join", timeout=5)

        if join_msg:
            assert user1["username"] in join_msg.get("admins", []), (
                f"Admin role lost after refresh. admins={join_msg.get('admins')}"
            )

        room2_msgs = await drain(room2, timeout=2)
        new_admin_msgs = [m for m in room2_msgs if m.get("type") == "new_admin"]
        auto_promoted = [m for m in new_admin_msgs if m.get("username") == user2["username"]]
        assert len(auto_promoted) == 0, "User2 was incorrectly auto-promoted"

        await room1_new.close()
        await room2.close()
        await lobby1.close()
        await lobby2.close()

    @pytest.mark.asyncio
    async def test_refresh_no_reconnect_loop(self, ws_url: str, user1: dict, test_room: dict):
        lobby = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room)

        await room.close()
        await asyncio.sleep(0.3)
        room_new = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])

        await room_new.send(json.dumps({"type": "message", "text": "after refresh"}))
        msgs = await drain(room_new, timeout=3)

        errors = [m for m in msgs if m.get("type") == "error"]
        assert len(errors) == 0, f"Got errors after reconnect: {errors}"
        assert room_new.open

        await room_new.close()
        await lobby.close()
