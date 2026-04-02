"""Private messaging tests — send, edit, delete, reactions, typing, files, DM removal."""

import asyncio
import json
import os
import tempfile
import time

import pytest
import websockets

from helpers import auth_header, ws_connect, recv_until, drain


class TestPMSendReceive:
    """Core PM flows via REST and WebSocket."""

    def test_send_pm(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "hello pm"},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "msg_id" in data

    @pytest.mark.asyncio
    async def test_pm_received_via_lobby_ws(self, ws_url: str, api, kong_url: str, user1: dict, user2: dict):
        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        await drain(lobby2)

        api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "ws delivery test"},
            headers=auth_header(user1["token"]),
        )

        msg = await recv_until(lobby2, "private_message", timeout=5)
        assert msg is not None, "Did not receive PM via lobby WebSocket"
        assert msg["from"] == user1["username"]
        assert msg["text"] == "ws delivery test"

        await lobby2.close()

    @pytest.mark.asyncio
    async def test_pm_typing_indicator(self, ws_url: str, user1: dict, user2: dict):
        lobby1 = await ws_connect(ws_url, "/ws/lobby", user1["token"])
        lobby2 = await ws_connect(ws_url, "/ws/lobby", user2["token"])
        await drain(lobby1)
        await drain(lobby2)

        await lobby1.send(json.dumps({
            "type": "typing_pm", "to": user2["username"]
        }))

        msg = await recv_until(lobby2, "typing_pm", timeout=3)
        assert msg is not None, "Did not receive PM typing indicator"
        assert msg["from"] == user1["username"]

        await lobby1.close()
        await lobby2.close()


class TestPMActions:
    """Edit, delete, reactions on PMs."""

    def test_edit_pm(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "to be edited"},
            headers=auth_header(user1["token"]),
        )
        msg_id = resp.json()["msg_id"]

        resp = api.patch(
            f"{kong_url}/pm/edit/{msg_id}",
            json={"text": "edited pm text"},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

    def test_delete_pm(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "to be deleted"},
            headers=auth_header(user1["token"]),
        )
        msg_id = resp.json()["msg_id"]

        resp = api.delete(
            f"{kong_url}/pm/delete/{msg_id}",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

    def test_add_pm_reaction(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "react to this pm"},
            headers=auth_header(user1["token"]),
        )
        msg_id = resp.json()["msg_id"]

        resp = api.post(
            f"{kong_url}/pm/reaction/{msg_id}",
            json={"emoji": "❤️"},
            headers=auth_header(user2["token"]),
        )
        assert resp.status_code == 200

    def test_remove_pm_reaction(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "remove reaction pm"},
            headers=auth_header(user1["token"]),
        )
        msg_id = resp.json()["msg_id"]

        api.post(
            f"{kong_url}/pm/reaction/{msg_id}",
            json={"emoji": "👍"},
            headers=auth_header(user2["token"]),
        )
        resp = api.delete(
            f"{kong_url}/pm/reaction/{msg_id}/👍",
            headers=auth_header(user2["token"]),
        )
        assert resp.status_code == 200


class TestPMHistory:
    """PM history, conversation deletion, DM removal."""

    def test_pm_history(self, api, kong_url: str, user1: dict, user2: dict):
        api.post(
            f"{kong_url}/pm/send",
            json={"to": user2["username"], "text": "history test"},
            headers=auth_header(user1["token"]),
        )
        # Poll for Kafka persistence (up to 10s)
        for _ in range(5):
            time.sleep(2)
            resp = api.get(
                f"{kong_url}/messages/pm/history/{user2['username']}",
                headers=auth_header(user1["token"]),
            )
            assert resp.status_code == 200
            messages = resp.json()
            if any("history test" in m.get("content", "") for m in messages):
                break
        else:
            assert False, f"PM 'history test' not found in history after 10s. Got: {[m.get('content','') for m in messages]}"

    def test_delete_pm_conversation(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.post(
            f"{kong_url}/messages/pm/delete-conversation",
            json={"other_user_id": user2["user_id"]},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

    def test_deleted_conversations_list(self, api, kong_url: str, user1: dict, user2: dict):
        resp = api.get(
            f"{kong_url}/messages/pm/deleted-conversations",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        deleted = resp.json()
        deleted_ids = [d["other_user_id"] for d in deleted]
        assert user2["user_id"] in deleted_ids

    def test_pm_file_upload(self, api, kong_url: str, user1: dict, user2: dict):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"PM file test content")
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                resp = api.post(
                    f"{kong_url}/files/upload?recipient={user2['username']}",
                    files={"file": ("pm-test.txt", f, "text/plain")},
                    headers={"Authorization": f"Bearer {user1['token']}"},
                )
            assert resp.status_code == 201
            data = resp.json()
            assert data["isPrivate"] is True
        finally:
            os.unlink(tmp_path)
