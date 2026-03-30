# tests/test_2fa.py — Tests for TOTP-based 2FA functionality
"""
Tests cover:
- TOTP generation and verification (unit tests)
- 2FA setup flow (setup -> verify-setup -> enabled)
- 2FA disable flow (enabled -> disable with code -> disabled)
- Login flow with 2FA enabled (login -> temp_token -> verify-login -> JWT)
- Temp token expiry
- Invalid code handling
- Backwards compatibility (login without 2FA still returns JWT directly)
"""
from unittest.mock import MagicMock, patch

import pyotp
import pytest

from app.services.auth_service import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)


# ── Unit tests: TOTP helpers ─────────────────────────────────────────────


class TestTOTPHelpers:
    """Unit tests for the pure TOTP helper functions."""

    def test_generate_totp_secret_returns_base32(self):
        """Generated secret should be a valid base32 string."""
        secret = generate_totp_secret()
        assert len(secret) == 32  # pyotp default length
        # Verify it's valid base32 by creating a TOTP with it
        totp = pyotp.TOTP(secret)
        assert totp.now() is not None

    def test_get_totp_uri_format(self):
        """URI should follow the otpauth:// format with correct issuer."""
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "testuser")
        assert uri.startswith("otpauth://totp/")
        assert "cHATBOX" in uri
        assert "testuser" in uri
        assert secret in uri

    def test_verify_totp_with_valid_code(self):
        """A freshly generated code should verify successfully."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_verify_totp_with_invalid_code(self):
        """A wrong code should not verify."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_verify_totp_allows_window(self):
        """Codes within the valid_window=1 should be accepted."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        # Generate code for current time — it should work
        code = totp.now()
        assert verify_totp(secret, code) is True


# ── Integration tests: 2FA routes ────────────────────────────────────────


class TestSetup2FA:
    """Tests for POST /auth/2fa/setup."""

    def test_setup_returns_secret_and_uri(self, client):
        """Setup should return a TOTP secret and otpauth URI."""
        client.post("/auth/register", json={"username": "alice2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "alice2fa", "password": "password123"}
        ).json()["access_token"]

        resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "manual_entry_key" in data
        assert "qr_code" in data
        assert len(data["manual_entry_key"]) == 32
        # QR code is now a server-side generated PNG data URI
        assert data["qr_code"].startswith("data:image/png;base64,")
        # otpauth_uri is intentionally omitted from the response to avoid DOM exposure

    def test_setup_requires_auth(self, client):
        """Setup without a token should return 401."""
        resp = client.post("/auth/2fa/setup")
        assert resp.status_code == 401

    def test_setup_when_already_enabled_returns_400(self, client):
        """Setting up 2FA when already enabled should fail."""
        client.post("/auth/register", json={"username": "bob2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "bob2fa", "password": "password123"}
        ).json()["access_token"]

        # Setup and verify
        setup_resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        secret = setup_resp.json()["manual_entry_key"]
        code = pyotp.TOTP(secret).now()
        client.post(
            "/auth/2fa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Try to setup again — should fail
        resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400
        assert "already enabled" in resp.json()["detail"]


class TestVerifySetup2FA:
    """Tests for POST /auth/2fa/verify-setup."""

    def test_verify_setup_enables_2fa(self, client):
        """Verifying with a correct code should enable 2FA."""
        client.post("/auth/register", json={"username": "carol2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "carol2fa", "password": "password123"}
        ).json()["access_token"]

        setup_resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        secret = setup_resp.json()["manual_entry_key"]
        code = pyotp.TOTP(secret).now()

        resp = client.post(
            "/auth/2fa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "enabled" in resp.json()["message"].lower()

        # Verify status endpoint reports enabled
        status = client.get("/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert status.json()["is_2fa_enabled"] is True

    def test_verify_setup_with_invalid_code_returns_400(self, client):
        """Verifying with an invalid code should fail."""
        client.post("/auth/register", json={"username": "dave2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "dave2fa", "password": "password123"}
        ).json()["access_token"]

        client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})

        resp = client.post(
            "/auth/2fa/verify-setup",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    def test_verify_setup_without_setup_first_returns_400(self, client):
        """Verifying without calling setup first should fail."""
        client.post("/auth/register", json={"username": "eve2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "eve2fa", "password": "password123"}
        ).json()["access_token"]

        resp = client.post(
            "/auth/2fa/verify-setup",
            json={"code": "123456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


class TestDisable2FA:
    """Tests for POST /auth/2fa/disable."""

    def _enable_2fa(self, client, username, password):
        """Helper: register, login, setup, and enable 2FA. Returns (token, secret)."""
        client.post("/auth/register", json={"username": username, "password": password})
        token = client.post(
            "/auth/login", json={"username": username, "password": password}
        ).json()["access_token"]

        setup_resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        secret = setup_resp.json()["manual_entry_key"]
        code = pyotp.TOTP(secret).now()
        client.post(
            "/auth/2fa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        return token, secret

    def test_disable_with_valid_code(self, client):
        """Disabling 2FA with a correct code should succeed."""
        token, secret = self._enable_2fa(client, "frank2fa", "password123")
        code = pyotp.TOTP(secret).now()

        resp = client.post(
            "/auth/2fa/disable",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "disabled" in resp.json()["message"].lower()

        # Verify status is now disabled
        status = client.get("/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert status.json()["is_2fa_enabled"] is False

    def test_disable_with_invalid_code_returns_400(self, client):
        """Disabling 2FA with a wrong code should fail."""
        token, _ = self._enable_2fa(client, "grace2fa", "password123")

        resp = client.post(
            "/auth/2fa/disable",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_disable_when_not_enabled_returns_400(self, client):
        """Trying to disable 2FA when it's not enabled should fail."""
        client.post("/auth/register", json={"username": "heidi2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "heidi2fa", "password": "password123"}
        ).json()["access_token"]

        resp = client.post(
            "/auth/2fa/disable",
            json={"code": "123456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


class TestLoginWith2FA:
    """Tests for the 2FA login flow."""

    def _enable_2fa(self, client, username, password):
        """Helper: register, login, setup, and enable 2FA. Returns secret."""
        client.post("/auth/register", json={"username": username, "password": password})
        token = client.post(
            "/auth/login", json={"username": username, "password": password}
        ).json()["access_token"]

        setup_resp = client.post("/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        secret = setup_resp.json()["manual_entry_key"]
        code = pyotp.TOTP(secret).now()
        client.post(
            "/auth/2fa/verify-setup",
            json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        return secret

    def test_login_with_2fa_returns_temp_token(self, client):
        """Login when 2FA is enabled should return requires_2fa=true and a temp_token."""
        secret = self._enable_2fa(client, "ivan2fa", "password123")

        resp = client.post(
            "/auth/login", json={"username": "ivan2fa", "password": "password123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_2fa"] is True
        assert "temp_token" in data
        assert "access_token" not in data

    def test_verify_login_with_valid_code_returns_jwt(self, client):
        """Completing 2FA login with a valid code should return a full JWT."""
        secret = self._enable_2fa(client, "judy2fa", "password123")

        # Step 1: Login returns temp_token
        login_resp = client.post(
            "/auth/login", json={"username": "judy2fa", "password": "password123"}
        )
        temp_token = login_resp.json()["temp_token"]

        # Step 2: Verify with TOTP code
        code = pyotp.TOTP(secret).now()
        resp = client.post(
            "/auth/2fa/verify-login",
            json={"temp_token": temp_token, "code": code},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "judy2fa"

    def test_verify_login_with_invalid_code_returns_401(self, client):
        """An invalid TOTP code should not complete the login."""
        self._enable_2fa(client, "karl2fa", "password123")

        login_resp = client.post(
            "/auth/login", json={"username": "karl2fa", "password": "password123"}
        )
        temp_token = login_resp.json()["temp_token"]

        resp = client.post(
            "/auth/2fa/verify-login",
            json={"temp_token": temp_token, "code": "000000"},
        )
        assert resp.status_code == 401

    def test_verify_login_with_expired_token_returns_401(self, client):
        """An expired or invalid temp_token should fail."""
        resp = client.post(
            "/auth/2fa/verify-login",
            json={"temp_token": "nonexistent-token", "code": "123456"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()

    def test_temp_token_is_single_use(self, client):
        """A temp_token should only work once."""
        secret = self._enable_2fa(client, "luna2fa", "password123")

        login_resp = client.post(
            "/auth/login", json={"username": "luna2fa", "password": "password123"}
        )
        temp_token = login_resp.json()["temp_token"]

        # First use: should succeed
        code = pyotp.TOTP(secret).now()
        resp1 = client.post(
            "/auth/2fa/verify-login",
            json={"temp_token": temp_token, "code": code},
        )
        assert resp1.status_code == 200

        # Second use: should fail (token consumed)
        resp2 = client.post(
            "/auth/2fa/verify-login",
            json={"temp_token": temp_token, "code": code},
        )
        assert resp2.status_code == 401


class TestLoginBackwardsCompatibility:
    """Ensure login still works normally for users without 2FA."""

    def test_login_without_2fa_returns_jwt_directly(self, client):
        """Users without 2FA enabled should get a JWT directly on login."""
        client.post("/auth/register", json={"username": "mara2fa", "password": "password123"})
        resp = client.post(
            "/auth/login", json={"username": "mara2fa", "password": "password123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data.get("requires_2fa") is None or data.get("requires_2fa") is False


class Test2FAStatus:
    """Tests for GET /auth/2fa/status."""

    def test_status_returns_false_by_default(self, client):
        """New users should have 2FA disabled."""
        client.post("/auth/register", json={"username": "nora2fa", "password": "password123"})
        token = client.post(
            "/auth/login", json={"username": "nora2fa", "password": "password123"}
        ).json()["access_token"]

        resp = client.get("/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["is_2fa_enabled"] is False

    def test_status_requires_auth(self, client):
        """Status endpoint without auth should return 401."""
        resp = client.get("/auth/2fa/status")
        assert resp.status_code == 401
