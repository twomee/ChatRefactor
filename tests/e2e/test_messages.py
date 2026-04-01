"""Message service tests — history, search, edit, delete, reactions, context, link preview."""

import asyncio
import json
import time

import pytest
import requests

from helpers import auth_header, ws_connect, recv_until, drain


@pytest.fixture(scope="module")
def sent_message(api, kong_url: str, ws_url: str, user1: dict, test_room: dict):
    """Send a message via WebSocket and return its msg_id after Kafka persists it."""
    async def _send():
        lobby = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        room = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
        await drain(room)

        text = f"e2e_msg_{int(time.time())}"
        await room.send(json.dumps({"type": "message", "text": text}))
        msg = await recv_until(room, "message", timeout=5)
        await room.close()
        await lobby.close()
        return {"msg_id": msg["msg_id"], "text": text}

    result = asyncio.run(_send())
    time.sleep(2)
    return result


class TestRoomHistory:
    """Room message history and replay."""

    @pytest.mark.smoke
    def test_get_room_history(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict, sent_message: dict):
        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}/history?limit=50",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        messages = resp.json()
        assert isinstance(messages, list)

    @pytest.mark.smoke
    def test_replay_with_since(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict):
        since = "2024-01-01T00:00:00Z"
        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}?since={since}&limit=50",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_history_without_auth(self, api: requests.Session, kong_url: str, test_room: dict):
        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}/history",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 401


class TestMessageActions:
    """Edit, delete, reactions via REST."""

    def test_edit_message(self, api: requests.Session, kong_url: str, user1: dict, sent_message: dict):
        resp = api.patch(
            f"{kong_url}/messages/edit/{sent_message['msg_id']}",
            json={"content": "edited via REST"},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 201
        assert resp.json()["edited"] is True

    def test_delete_message(self, api: requests.Session, kong_url: str, user1: dict, ws_url: str, test_room: dict):
        async def _send():
            lobby = await ws_connect(ws_url, "/ws/lobby", user1["token"])
            room = await ws_connect(ws_url, f"/ws/{test_room['id']}", user1["token"])
            await drain(room)
            await room.send(json.dumps({"type": "message", "text": "delete me via REST"}))
            msg = await recv_until(room, "message", timeout=5)
            await room.close()
            await lobby.close()
            return msg["msg_id"]

        msg_id = asyncio.run(_send())
        time.sleep(2)

        resp = api.delete(
            f"{kong_url}/messages/delete/{msg_id}",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_reactions(self, api: requests.Session, kong_url: str, user1: dict, sent_message: dict):
        resp = api.get(
            f"{kong_url}/messages/{sent_message['msg_id']}/reactions",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSearch:
    """Message search."""

    def test_search_messages(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict, sent_message: dict):
        resp = api.get(
            f"{kong_url}/messages/search",
            params={"q": sent_message["text"], "room_id": test_room["id"], "limit": 10},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)


class TestContext:
    """Message context endpoints."""

    def test_room_message_context(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict, sent_message: dict):
        resp = api.get(
            f"{kong_url}/messages/rooms/{test_room['id']}/context",
            params={"message_id": sent_message["msg_id"], "before": 5, "after": 5},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_pm_context(self, api: requests.Session, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "context test pm"},
            headers=auth_header(user1["token"]),
        )
        msg_id = resp.json()["msg_id"]
        time.sleep(2)

        resp = api.get(
            f"{kong_url}/messages/pm/context",
            params={"message_id": msg_id, "before": 5, "after": 5},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_pm_history_endpoint(self, api: requests.Session, kong_url: str, user1: dict, user2: dict):
        resp = api.get(
            f"{kong_url}/messages/pm/history/{user2['username']}",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestLinkPreview:
    """Link preview metadata fetching."""

    def test_link_preview(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.get(
            f"{kong_url}/messages/preview",
            params={"url": "https://github.com"},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "title" in data
        assert "url" in data
