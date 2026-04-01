"""Admin dashboard tests — global admin actions."""

import pytest
import requests

from conftest import auth_header


class TestAdminRoomManagement:
    """Admin room listing and control."""

    def test_list_all_rooms_including_inactive(self, api: requests.Session, kong_url: str, admin_token: str):
        resp = api.get(
            f"{kong_url}/admin/rooms",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        rooms = resp.json()
        assert isinstance(rooms, list)
        assert len(rooms) >= 3

    def test_list_online_users(self, api: requests.Session, kong_url: str, admin_token: str):
        resp = api.get(
            f"{kong_url}/admin/users",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "all_online" in data
        assert "per_room" in data

    def test_close_and_open_specific_room(self, api: requests.Session, kong_url: str, admin_token: str, timestamp: str):
        resp = api.post(
            f"{kong_url}/rooms",
            json={"name": f"adminclose_{timestamp}"},
            headers=auth_header(admin_token),
        )
        room_id = resp.json()["id"]

        resp = api.post(
            f"{kong_url}/admin/rooms/{room_id}/close",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["room_id"] == room_id

        resp = api.post(
            f"{kong_url}/admin/rooms/{room_id}/open",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["room_id"] == room_id

    def test_close_all_rooms(self, api: requests.Session, kong_url: str, admin_token: str):
        resp = api.post(
            f"{kong_url}/admin/chat/close",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert "affected" in resp.json()

    def test_open_all_rooms(self, api: requests.Session, kong_url: str, admin_token: str):
        resp = api.post(
            f"{kong_url}/admin/chat/open",
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert "affected" in resp.json()


class TestAdminUserManagement:
    """Admin user promotion and access control."""

    def test_promote_user_to_global_admin(self, api: requests.Session, kong_url: str, admin_token: str, user3: dict):
        resp = api.post(
            f"{kong_url}/admin/promote",
            params={"username": user3["username"]},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == user3["username"]

    def test_non_admin_access_forbidden(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.get(
            f"{kong_url}/admin/rooms",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 403

    def test_non_admin_cannot_close_rooms(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/admin/chat/close",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 403
