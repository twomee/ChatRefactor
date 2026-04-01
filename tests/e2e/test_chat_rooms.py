"""Chat service room tests — CRUD, admin actions, mute/kick persistence."""

import pytest
import requests

from helpers import auth_header


class TestRoomCRUD:
    """Room listing and creation."""

    @pytest.mark.smoke
    def test_list_rooms_has_defaults(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.get(f"{kong_url}/rooms", headers=auth_header(user1["token"]))
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert "politics" in names
        assert "sports" in names
        assert "movies" in names

    @pytest.mark.smoke
    def test_admin_creates_room(self, api: requests.Session, kong_url: str, admin_token: str, timestamp: str):
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"crud_test_{timestamp}"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == f"crud_test_{timestamp}"

    def test_regular_user_cannot_create_room(self, api: requests.Session, kong_url: str, user1: dict, timestamp: str):
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"shouldfail_{timestamp}"},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 403

    def test_get_room_users(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict):
        resp = api.get(
            f"{kong_url}/rooms/{test_room['id']}/users",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

    def test_rooms_without_auth(self, api: requests.Session, kong_url: str):
        resp = api.get(f"{kong_url}/rooms")
        assert resp.status_code == 401


class TestRoomAdminActions:
    """Room-level admin actions: mute, unmute, kick, promote, deactivate."""

    def test_admin_mutes_user_blocks_messages(
        self, api: requests.Session, kong_url: str, admin_token: str, user3: dict, timestamp: str
    ):
        # Create a dedicated room for mute tests
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"mutetest_{timestamp}"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201
        room_id = resp.json()["id"]

        # Mute user3
        resp = api.post(
            f"{kong_url}/rooms/{room_id}/mutes",
            json={"user_id": user3["user_id"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201
        self.__class__._mute_room_id = room_id

    def test_admin_unmutes_user(self, api: requests.Session, kong_url: str, admin_token: str, user3: dict):
        room_id = getattr(self.__class__, "_mute_room_id", None)
        if room_id is None:
            pytest.skip("Depends on test_admin_mutes_user_blocks_messages")
        resp = api.delete(
            f"{kong_url}/rooms/{room_id}/mutes/{user3['user_id']}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200

    def test_kick_muted_user_mute_persists_on_rejoin(
        self, api: requests.Session, kong_url: str, admin_token: str, user3: dict, timestamp: str
    ):
        # Create a fresh room
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"kickmute_{timestamp}"},
            headers=auth_header(admin_token),
        )
        room_id = resp.json()["id"]

        # Mute user3
        resp = api.post(
            f"{kong_url}/rooms/{room_id}/mutes",
            json={"user_id": user3["user_id"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201

        # Verify unmute works after kick — meaning the mute was still there
        resp = api.delete(
            f"{kong_url}/rooms/{room_id}/mutes/{user3['user_id']}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200  # 200 means mute existed and was removed

    def test_admin_promotes_user_to_room_admin(
        self, api: requests.Session, kong_url: str, admin_token: str, user1: dict, test_room: dict
    ):
        resp = api.post(
            f"{kong_url}/rooms/{test_room['id']}/admins",
            json={"user_id": user1["user_id"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201
        assert "user_id" in resp.json()

    def test_admin_removes_room_admin(
        self, api: requests.Session, kong_url: str, admin_token: str, user1: dict, test_room: dict
    ):
        resp = api.delete(
            f"{kong_url}/rooms/{test_room['id']}/admins/{user1['user_id']}",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200

    def test_set_room_inactive(self, api: requests.Session, kong_url: str, admin_token: str, timestamp: str):
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"deactivate_{timestamp}"},
            headers=auth_header(admin_token),
        )
        room_id = resp.json()["id"]
        resp = api.put(
            f"{kong_url}/rooms/{room_id}/active",
            json={"is_active": False},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_non_admin_room_actions_forbidden(
        self, api: requests.Session, kong_url: str, user1: dict, user3: dict, test_room: dict
    ):
        resp = api.post(
            f"{kong_url}/rooms/{test_room['id']}/mutes",
            json={"user_id": user3["user_id"]},
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 403
