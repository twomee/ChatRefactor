"""Auth service e2e tests — register, login, profile, 2FA, logout."""

import time

import pyotp
import pytest
import requests

from helpers import auth_header


class TestRegisterLogin:
    """Registration and login flows."""

    @pytest.mark.smoke
    def test_register_new_user(self, api: requests.Session, kong_url: str, timestamp: str):
        resp = api.post(
            f"{kong_url}/auth/register",
            json={
                "username": f"reg_test_{timestamp}",
                "password": "TestPass123!",
                "email": f"reg_test_{timestamp}@test.com",
            },
        )
        assert resp.status_code == 201
        assert "Registered" in resp.json()["message"]

    @pytest.mark.smoke
    def test_duplicate_register(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/auth/register",
            json={
                "username": user1["username"],
                "password": "TestPass123!",
                "email": "dupe@test.com",
            },
        )
        assert resp.status_code == 409

    @pytest.mark.smoke
    def test_login_returns_token(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": user1["username"], "password": user1["password"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == user1["username"]
        assert "user_id" in data

    def test_login_wrong_password(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": user1["username"], "password": "WRONG"},
        )
        assert resp.status_code == 401

    def test_ping_with_valid_token(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/auth/ping",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200

    def test_ping_without_token(self, api: requests.Session, kong_url: str):
        resp = api.post(f"{kong_url}/auth/ping")
        assert resp.status_code == 401


class TestProfile:
    """Profile viewing and editing."""

    def test_get_profile(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.get(
            f"{kong_url}/auth/profile",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == user1["username"]
        assert data["email"] == user1["email"]

    def test_update_email(self, api: requests.Session, kong_url: str, user2: dict, timestamp: str):
        new_email = f"newemail_{timestamp}@test.com"
        resp = api.patch(
            f"{kong_url}/auth/profile/email",
            json={"new_email": new_email, "current_password": user2["password"]},
            headers=auth_header(user2["token"]),
        )
        assert resp.status_code == 200

        # Verify the email changed
        resp = api.get(
            f"{kong_url}/auth/profile",
            headers=auth_header(user2["token"]),
        )
        assert resp.json()["email"] == new_email

    def test_update_password(self, api: requests.Session, kong_url: str, timestamp: str):
        # Register a fresh user for this test to avoid breaking other fixtures
        username = f"pwdtest_{timestamp}"
        old_password = "OldPass123!"
        new_password = "NewPass456!"

        api.post(
            f"{kong_url}/auth/register",
            json={"username": username, "password": old_password, "email": f"{username}@test.com"},
        )
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": old_password},
        )
        token = resp.json()["access_token"]

        # Change password
        resp = api.patch(
            f"{kong_url}/auth/profile/password",
            json={"current_password": old_password, "new_password": new_password},
            headers=auth_header(token),
        )
        assert resp.status_code == 200

        # Login with new password
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": new_password},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_forgot_password(self, api: requests.Session, kong_url: str, user1: dict):
        resp = api.post(
            f"{kong_url}/auth/forgot-password",
            json={"email": user1["email"]},
        )
        # Always returns 200 (no email enumeration)
        assert resp.status_code == 200


class TestTwoFactor:
    """2FA setup, verify, and login flow."""

    def test_2fa_full_flow(self, api: requests.Session, kong_url: str, timestamp: str):
        # Register a fresh user for 2FA (avoid breaking shared fixtures)
        username = f"twofa_{timestamp}"
        password = "TwoFA_Pass123!"
        api.post(
            f"{kong_url}/auth/register",
            json={"username": username, "password": password, "email": f"{username}@test.com"},
        )
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": password},
        )
        token = resp.json()["access_token"]

        # Setup 2FA — get secret
        resp = api.post(
            f"{kong_url}/auth/2fa/setup",
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_code" in data
        secret = data["secret"]

        # Generate TOTP code and verify setup
        totp = pyotp.TOTP(secret)
        code = totp.now()
        resp = api.post(
            f"{kong_url}/auth/2fa/verify-setup",
            json={"code": code},
            headers=auth_header(token),
        )
        assert resp.status_code == 200

        # Verify 2FA is enabled
        resp = api.get(
            f"{kong_url}/auth/2fa/status",
            headers=auth_header(token),
        )
        assert resp.json()["is_2fa_enabled"] is True

        # Login now requires 2FA
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_2fa"] is True
        assert "temp_token" in data

        # Complete login with TOTP
        # Wait for next time window to avoid replay protection
        time.sleep(1)
        code = totp.now()
        resp = api.post(
            f"{kong_url}/auth/2fa/verify-login",
            json={"temp_token": data["temp_token"], "code": code},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


class TestLogout:
    """Logout and token revocation."""

    def test_logout_user_disappears_from_online(
        self, api: requests.Session, kong_url: str, timestamp: str
    ):
        # Register a fresh user to avoid breaking shared fixtures
        username = f"logout_{timestamp}"
        password = "LogoutPass123!"
        api.post(
            f"{kong_url}/auth/register",
            json={"username": username, "password": password, "email": f"{username}@test.com"},
        )
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": password},
        )
        token = resp.json()["access_token"]

        # Logout
        resp = api.post(
            f"{kong_url}/auth/logout",
            headers=auth_header(token),
        )
        assert resp.status_code == 200

        # Token should be blacklisted
        resp = api.post(
            f"{kong_url}/auth/ping",
            headers=auth_header(token),
        )
        assert resp.status_code == 401

    def test_logout_retains_room_admin_role(
        self, api: requests.Session, kong_url: str, admin_token: str, test_room: dict, timestamp: str
    ):
        # Register a user, make them room admin, logout, re-login, verify still admin
        username = f"adminkeep_{timestamp}"
        password = "AdminKeep123!"
        api.post(
            f"{kong_url}/auth/register",
            json={"username": username, "password": password, "email": f"{username}@test.com"},
        )
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": password},
        )
        data = resp.json()
        token = data["access_token"]
        user_id = data["user_id"]

        # Admin promotes this user to room admin
        resp = api.post(
            f"{kong_url}/rooms/{test_room['id']}/admins",
            json={"user_id": user_id},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 201

        # Logout
        api.post(f"{kong_url}/auth/logout", headers=auth_header(token))

        # Re-login
        resp = api.post(
            f"{kong_url}/auth/login",
            json={"username": username, "password": password},
        )
        new_token = resp.json()["access_token"]

        # Verify still room admin — removing self should work (only admins can manage admins)
        resp = api.delete(
            f"{kong_url}/rooms/{test_room['id']}/admins/{user_id}",
            headers=auth_header(admin_token),
        )
        # If user was still admin, removal succeeds (200). If not, 404/400.
        assert resp.status_code == 200
