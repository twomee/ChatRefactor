# tests/test_profile_and_reset.py — Tests for email registration, profile editing, and forgot password
"""
Comprehensive tests covering:
- Registration with email (valid, missing email, duplicate email)
- Get profile (returns username + email)
- Update email (success, wrong password, duplicate email)
- Update password (success, wrong current password, validation)
- Forgot password (existing email, non-existing email -- both return 200)
- Reset password (valid token, expired token, used token, invalid token)
- Email service (console sender logs, SMTP sender initialization)
- Password reset DAL (create, get valid, mark used, cleanup)
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import hash_password
from app.dal import password_reset_dal, user_dal
from app.services.email_service import (
    ConsoleEmailSender,
    SMTPEmailSender,
    create_email_sender,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Helper: register + login and return auth header
# ═══════════════════════════════════════════════════════════════════════════


def _register_and_login(client, username, password, email):
    """Register a user, log in, return the Authorization header dict."""
    client.post(
        "/auth/register",
        json={"username": username, "password": password, "email": email},
    )
    token = client.post(
        "/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  Feature #6: Email Registration
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailRegistration:
    """Tests for POST /auth/register with the email field."""

    def test_register_with_email_success(self, client):
        """Registration with a valid email should succeed and return 201."""
        resp = client.post(
            "/auth/register",
            json={
                "username": "emailuser1",
                "password": "password123",
                "email": "emailuser1@example.com",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["message"] == "Registered successfully"

    def test_register_without_email_returns_422(self, client):
        """Registration without an email should be rejected (email is required)."""
        resp = client.post(
            "/auth/register",
            json={"username": "emailuser2", "password": "password123"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email_returns_422(self, client):
        """Registration with an invalid email format should be rejected."""
        resp = client.post(
            "/auth/register",
            json={
                "username": "emailuser3",
                "password": "password123",
                "email": "not-an-email",
            },
        )
        assert resp.status_code == 422

    def test_register_duplicate_email_returns_409(self, client):
        """Registration with an email already used by another user should return 409."""
        client.post(
            "/auth/register",
            json={
                "username": "emailuser4",
                "password": "password123",
                "email": "duplicate@example.com",
            },
        )
        resp = client.post(
            "/auth/register",
            json={
                "username": "emailuser5",
                "password": "password123",
                "email": "duplicate@example.com",
            },
        )
        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower()

    def test_user_response_includes_email(self, client):
        """The internal user lookup should include the email field."""
        client.post(
            "/auth/register",
            json={
                "username": "emailuser6",
                "password": "password123",
                "email": "emailuser6@example.com",
            },
        )
        resp = client.get("/auth/users/by-username/emailuser6")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "emailuser6@example.com"


# ═══════════════════════════════════════════════════════════════════════════
#  Feature #7: Profile (Get, Update Email, Update Password)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetProfile:
    """Tests for GET /auth/profile."""

    def test_get_profile_returns_username_and_email(self, client):
        """Authenticated user should see their username and email."""
        headers = _register_and_login(
            client, "profile1", "password123", "profile1@example.com"
        )
        resp = client.get("/auth/profile", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "profile1"
        assert data["email"] == "profile1@example.com"

    def test_get_profile_requires_auth(self, client):
        """GET /auth/profile without a token should return 401."""
        resp = client.get("/auth/profile")
        assert resp.status_code == 401


class TestUpdateEmail:
    """Tests for PATCH /auth/profile/email."""

    def test_update_email_success(self, client):
        """Providing the correct password should update the email."""
        headers = _register_and_login(
            client, "emailup1", "password123", "old@example.com"
        )
        resp = client.patch(
            "/auth/profile/email",
            json={"new_email": "new@example.com", "current_password": "password123"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

        # Verify the email actually changed
        profile = client.get("/auth/profile", headers=headers).json()
        assert profile["email"] == "new@example.com"

    def test_update_email_wrong_password_returns_401(self, client):
        """Wrong current password should be rejected."""
        headers = _register_and_login(
            client, "emailup2", "password123", "emailup2@example.com"
        )
        resp = client.patch(
            "/auth/profile/email",
            json={"new_email": "new2@example.com", "current_password": "wrongpassword"},
            headers=headers,
        )
        assert resp.status_code == 401

    def test_update_email_duplicate_returns_409(self, client):
        """Changing to an email already used by another user should return 409."""
        _register_and_login(client, "emailup3", "password123", "taken@example.com")
        headers = _register_and_login(
            client, "emailup4", "password123", "emailup4@example.com"
        )
        resp = client.patch(
            "/auth/profile/email",
            json={"new_email": "taken@example.com", "current_password": "password123"},
            headers=headers,
        )
        assert resp.status_code == 409

    def test_update_email_invalid_format_returns_422(self, client):
        """An invalid email format should be rejected by Pydantic."""
        headers = _register_and_login(
            client, "emailup5", "password123", "emailup5@example.com"
        )
        resp = client.patch(
            "/auth/profile/email",
            json={"new_email": "not-valid", "current_password": "password123"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_email_requires_auth(self, client):
        """PATCH /auth/profile/email without a token should return 401."""
        resp = client.patch(
            "/auth/profile/email",
            json={"new_email": "x@example.com", "current_password": "password123"},
        )
        assert resp.status_code == 401


class TestUpdatePassword:
    """Tests for PATCH /auth/profile/password."""

    def test_update_password_success(self, client):
        """Providing the correct current password should update to the new password."""
        headers = _register_and_login(
            client, "pwup1", "oldpassword1", "pwup1@example.com"
        )
        resp = client.patch(
            "/auth/profile/password",
            json={"current_password": "oldpassword1", "new_password": "newpassword1"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

        # Verify the new password works for login
        login_resp = client.post(
            "/auth/login", json={"username": "pwup1", "password": "newpassword1"}
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()

    def test_update_password_wrong_current_returns_401(self, client):
        """Wrong current password should be rejected."""
        headers = _register_and_login(
            client, "pwup2", "password123", "pwup2@example.com"
        )
        resp = client.patch(
            "/auth/profile/password",
            json={"current_password": "wrongpass1", "new_password": "newpassword1"},
            headers=headers,
        )
        assert resp.status_code == 401

    def test_update_password_too_short_returns_422(self, client):
        """A new password shorter than 8 characters should be rejected."""
        headers = _register_and_login(
            client, "pwup3", "password123", "pwup3@example.com"
        )
        resp = client.patch(
            "/auth/profile/password",
            json={"current_password": "password123", "new_password": "short"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_password_requires_auth(self, client):
        """PATCH /auth/profile/password without a token should return 401."""
        resp = client.patch(
            "/auth/profile/password",
            json={"current_password": "x", "new_password": "newpassword1"},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
#  Feature #11: Forgot / Reset Password
# ═══════════════════════════════════════════════════════════════════════════


class TestForgotPassword:
    """Tests for POST /auth/forgot-password."""

    def test_forgot_password_existing_email_returns_200(self, client):
        """Requesting a reset for a registered email should return 200."""
        client.post(
            "/auth/register",
            json={
                "username": "forgot1",
                "password": "password123",
                "email": "forgot1@example.com",
            },
        )
        resp = client.post(
            "/auth/forgot-password",
            json={"email": "forgot1@example.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_forgot_password_unknown_email_returns_200(self, client):
        """Requesting a reset for an unknown email should also return 200 (no enumeration)."""
        resp = client.post(
            "/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_forgot_password_invalid_email_returns_422(self, client):
        """An invalid email format should be rejected."""
        resp = client.post(
            "/auth/forgot-password",
            json={"email": "not-valid"},
        )
        assert resp.status_code == 422


class TestResetPassword:
    """Tests for POST /auth/reset-password."""

    def test_reset_password_valid_token(self, client):
        """A valid reset token should allow the user to set a new password."""
        # Register a user
        client.post(
            "/auth/register",
            json={
                "username": "reset1",
                "password": "oldpassword1",
                "email": "reset1@example.com",
            },
        )
        # Request forgot password and capture the token from the DAL
        with patch(
            "app.services.password_reset_service.secrets.token_hex",
            return_value="a" * 64,
        ):
            client.post(
                "/auth/forgot-password",
                json={"email": "reset1@example.com"},
            )

        # Use the captured token to reset the password
        resp = client.post(
            "/auth/reset-password",
            json={"token": "a" * 64, "new_password": "newpassword1"},
        )
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

        # Verify the new password works
        login_resp = client.post(
            "/auth/login", json={"username": "reset1", "password": "newpassword1"}
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()

    def test_reset_password_invalid_token_returns_400(self, client):
        """An invalid/non-existent token should return 400."""
        resp = client.post(
            "/auth/reset-password",
            json={"token": "bogus-token", "new_password": "newpassword1"},
        )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    def test_reset_password_expired_token_returns_400(self, client, db_session):
        """An expired token should return 400."""
        # Create a user and an expired token directly via DAL
        user = user_dal.create(
            db_session, "reset_exp", hash_password("password123"), email="reset_exp@example.com"
        )
        expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
        password_reset_dal.create_token(db_session, user.id, "expired-token-123", expired_time)

        resp = client.post(
            "/auth/reset-password",
            json={"token": "expired-token-123", "new_password": "newpassword1"},
        )
        assert resp.status_code == 400

    def test_reset_password_used_token_returns_400(self, client, db_session):
        """A token that has already been used should return 400."""
        user = user_dal.create(
            db_session, "reset_used", hash_password("password123"), email="reset_used@example.com"
        )
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "used-token-456", future_time)
        password_reset_dal.mark_token_used(db_session, "used-token-456")

        resp = client.post(
            "/auth/reset-password",
            json={"token": "used-token-456", "new_password": "newpassword1"},
        )
        assert resp.status_code == 400

    def test_reset_password_short_password_returns_422(self, client):
        """A password shorter than 8 characters should be rejected."""
        resp = client.post(
            "/auth/reset-password",
            json={"token": "any-token", "new_password": "short"},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
#  Email Service Unit Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestConsoleEmailSender:
    """Tests for the ConsoleEmailSender."""

    def test_console_sender_logs_email(self, caplog):
        """ConsoleEmailSender should log the email details."""
        sender = ConsoleEmailSender()
        with caplog.at_level(logging.INFO):
            sender.send("user@example.com", "Test Subject", "<p>Hello</p>")
        assert "user@example.com" in caplog.text
        assert "Test Subject" in caplog.text

    def test_console_sender_does_not_raise(self):
        """ConsoleEmailSender.send() should not raise exceptions."""
        sender = ConsoleEmailSender()
        # Should complete without error
        sender.send("user@example.com", "Subject", "Body")


class TestSMTPEmailSender:
    """Tests for the SMTPEmailSender initialization."""

    def test_smtp_sender_stores_config(self):
        """SMTPEmailSender should store its configuration for later use."""
        sender = SMTPEmailSender(
            host="smtp.example.com",
            port=587,
            username="user",
            password="",
            from_addr="noreply@example.com",
        )
        assert sender.host == "smtp.example.com"
        assert sender.port == 587
        assert sender.username == "user"
        assert sender.password == ""
        assert sender.from_addr == "noreply@example.com"

    def test_send_constructs_and_delivers_email(self):
        """send() should open an SMTP connection and deliver the message."""
        from unittest.mock import MagicMock, patch

        sender = SMTPEmailSender(
            host="smtp.example.com",
            port=587,
            username="user",
            password="",
            from_addr="noreply@example.com",
        )

        mock_server = MagicMock()
        with patch("smtplib.SMTP") as MockSMTP:
            MockSMTP.return_value.__enter__ = lambda s: mock_server
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            sender.send("recipient@example.com", "Hello", "<p>body</p>")

        MockSMTP.assert_called_once_with("smtp.example.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "")
        mock_server.send_message.assert_called_once()


class TestCreateEmailSender:
    """Tests for the create_email_sender() factory."""

    def test_returns_console_sender_when_no_smtp_host(self):
        """Without SMTP_HOST env var, should return ConsoleEmailSender."""
        with patch.dict("os.environ", {}, clear=False):
            # Make sure SMTP_HOST is not set
            import os

            os.environ.pop("SMTP_HOST", None)
            sender = create_email_sender()
        assert isinstance(sender, ConsoleEmailSender)

    def test_returns_smtp_sender_when_smtp_host_set(self):
        """With SMTP_HOST env var set, should return SMTPEmailSender."""
        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "myuser",
            "SMTP_PASSWORD": "",  # empty — test only verifies sender type, not credentials
            "SMTP_FROM": "sender@example.com",
        }
        with patch.dict("os.environ", env, clear=False):
            sender = create_email_sender()
        assert isinstance(sender, SMTPEmailSender)
        assert sender.host == "smtp.example.com"
        assert sender.port == 465


# ═══════════════════════════════════════════════════════════════════════════
#  Password Reset DAL Unit Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPasswordResetDAL:
    """Tests for app/dal/password_reset_dal.py functions."""

    def test_create_token(self, db_session):
        """create_token should persist a token and return it."""
        user = user_dal.create(
            db_session, "dal_user1", hash_password("password123"), email="dal1@test.com"
        )
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        token_obj = password_reset_dal.create_token(
            db_session, user.id, "test-token-abc", expires
        )
        assert token_obj.id is not None
        assert token_obj.user_id == user.id
        assert token_obj.token == "test-token-abc"
        assert token_obj.used is False

    def test_get_valid_token_returns_token(self, db_session):
        """get_valid_token should return a token that is not expired and not used."""
        user = user_dal.create(
            db_session, "dal_user2", hash_password("password123"), email="dal2@test.com"
        )
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "valid-token-xyz", expires)

        found = password_reset_dal.get_valid_token(db_session, "valid-token-xyz")
        assert found is not None
        assert found.token == "valid-token-xyz"

    def test_get_valid_token_returns_none_for_expired(self, db_session):
        """get_valid_token should return None for an expired token."""
        user = user_dal.create(
            db_session, "dal_user3", hash_password("password123"), email="dal3@test.com"
        )
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "expired-token-xyz", expired)

        found = password_reset_dal.get_valid_token(db_session, "expired-token-xyz")
        assert found is None

    def test_get_valid_token_returns_none_for_used(self, db_session):
        """get_valid_token should return None for a used token."""
        user = user_dal.create(
            db_session, "dal_user4", hash_password("password123"), email="dal4@test.com"
        )
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "used-token-xyz", expires)
        password_reset_dal.mark_token_used(db_session, "used-token-xyz")

        found = password_reset_dal.get_valid_token(db_session, "used-token-xyz")
        assert found is None

    def test_get_valid_token_returns_none_for_nonexistent(self, db_session):
        """get_valid_token should return None for a non-existent token."""
        found = password_reset_dal.get_valid_token(db_session, "does-not-exist")
        assert found is None

    def test_mark_token_used(self, db_session):
        """mark_token_used should set the used flag to True."""
        user = user_dal.create(
            db_session, "dal_user5", hash_password("password123"), email="dal5@test.com"
        )
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "mark-used-xyz", expires)
        password_reset_dal.mark_token_used(db_session, "mark-used-xyz")

        # After marking as used, get_valid_token should return None
        found = password_reset_dal.get_valid_token(db_session, "mark-used-xyz")
        assert found is None

    def test_cleanup_expired_removes_old_tokens(self, db_session):
        """cleanup_expired should delete expired and used tokens."""
        user = user_dal.create(
            db_session, "dal_user6", hash_password("password123"), email="dal6@test.com"
        )
        expired = datetime.now(timezone.utc) - timedelta(hours=2)
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        # Create one expired, one used, and one valid
        password_reset_dal.create_token(db_session, user.id, "cleanup-expired", expired)
        password_reset_dal.create_token(db_session, user.id, "cleanup-used", future)
        password_reset_dal.mark_token_used(db_session, "cleanup-used")
        password_reset_dal.create_token(db_session, user.id, "cleanup-valid", future)

        removed = password_reset_dal.cleanup_expired(db_session)
        assert removed == 2  # expired + used

        # The valid token should still exist
        found = password_reset_dal.get_valid_token(db_session, "cleanup-valid")
        assert found is not None


# ═══════════════════════════════════════════════════════════════════════════
#  User DAL: new email-related functions
# ═══════════════════════════════════════════════════════════════════════════


class TestUserDALEmail:
    """Tests for new email-related functions in user_dal."""

    def test_get_by_email_returns_user(self, db_session):
        """get_by_email should return the user when the email exists."""
        user_dal.create(
            db_session, "emaildal1", hash_password("pass123"), email="emaildal1@test.com"
        )
        found = user_dal.get_by_email(db_session, "emaildal1@test.com")
        assert found is not None
        assert found.username == "emaildal1"

    def test_get_by_email_case_insensitive(self, db_session):
        """get_by_email should be case-insensitive."""
        user_dal.create(
            db_session, "emaildal2", hash_password("pass123"), email="CaseTest@Test.com"
        )
        found = user_dal.get_by_email(db_session, "casetest@test.com")
        assert found is not None

    def test_get_by_email_returns_none_when_not_found(self, db_session):
        """get_by_email should return None for a non-existent email."""
        found = user_dal.get_by_email(db_session, "nobody@test.com")
        assert found is None

    def test_create_user_with_email(self, db_session):
        """create() should persist the email field."""
        user = user_dal.create(
            db_session, "emaildal3", hash_password("pass123"), email="emaildal3@test.com"
        )
        assert user.email == "emaildal3@test.com"

    def test_update_email(self, db_session):
        """update_email should change the user's email address."""
        user = user_dal.create(
            db_session, "emaildal4", hash_password("pass123"), email="old@test.com"
        )
        user_dal.update_email(db_session, user.id, "new@test.com")
        updated = user_dal.get_by_id(db_session, user.id)
        assert updated.email == "new@test.com"

    def test_update_password(self, db_session):
        """update_password should change the user's password hash."""
        user = user_dal.create(
            db_session, "emaildal5", hash_password("oldpass123"), email="emaildal5@test.com"
        )
        new_hash = hash_password("newpass123")
        user_dal.update_password(db_session, user.id, new_hash)
        updated = user_dal.get_by_id(db_session, user.id)
        assert updated.password_hash == new_hash


# ═══════════════════════════════════════════════════════════════════════════
#  Password Reset Service Unit Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPasswordResetService:
    """Tests for app/services/password_reset_service.py functions."""

    def test_request_reset_sends_email_for_existing_user(self, db_session):
        """request_reset should call email_sender.send() when the email matches a user."""
        from app.services.password_reset_service import request_reset

        user_dal.create(
            db_session, "prs_user1", hash_password("pass123"), email="prs1@test.com"
        )
        mock_sender = MagicMock()
        result = request_reset(db_session, "prs1@test.com", mock_sender)

        assert "reset link" in result["message"].lower()
        mock_sender.send.assert_called_once()
        # Verify the email was sent to the right address
        call_args = mock_sender.send.call_args
        assert call_args[0][0] == "prs1@test.com"

    def test_request_reset_no_email_for_unknown_user(self, db_session):
        """request_reset should NOT call email_sender.send() for unknown emails."""
        from app.services.password_reset_service import request_reset

        mock_sender = MagicMock()
        result = request_reset(db_session, "unknown@test.com", mock_sender)

        assert "reset link" in result["message"].lower()
        mock_sender.send.assert_not_called()

    def test_request_reset_handles_email_send_failure(self, db_session):
        """request_reset should not fail even if the email sender raises an exception."""
        from app.services.password_reset_service import request_reset

        user_dal.create(
            db_session, "prs_user2", hash_password("pass123"), email="prs2@test.com"
        )
        mock_sender = MagicMock()
        mock_sender.send.side_effect = Exception("SMTP down")
        result = request_reset(db_session, "prs2@test.com", mock_sender)

        # Should still return success (token was created)
        assert "reset link" in result["message"].lower()

    def test_reset_password_success(self, db_session):
        """reset_password should update the user's password and mark the token as used."""
        from app.services.password_reset_service import reset_password

        user = user_dal.create(
            db_session, "prs_user3", hash_password("oldpass123"), email="prs3@test.com"
        )
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        password_reset_dal.create_token(db_session, user.id, "reset-service-tok", expires)

        result = reset_password(db_session, "reset-service-tok", "newpass123")
        assert "reset" in result["message"].lower()

        # Token should now be used
        found = password_reset_dal.get_valid_token(db_session, "reset-service-tok")
        assert found is None

    def test_reset_password_invalid_token_raises_400(self, db_session):
        """reset_password should raise 400 for an invalid token."""
        from fastapi import HTTPException

        from app.services.password_reset_service import reset_password

        with pytest.raises(HTTPException) as exc_info:
            reset_password(db_session, "invalid-token-xyz", "newpass123")
        assert exc_info.value.status_code == 400
