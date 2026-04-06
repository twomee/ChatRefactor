# tests/test_schemas_auth.py — Pydantic schema validation tests for app/schemas/auth.py
"""
Tests for:
- UserRegister: username too long, password too long
- UserLogin: empty username, empty password, username too long, password too long
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import UserLogin, UserRegister


class TestUserRegisterValidation:
    """Tests for UserRegister schema validation."""

    def test_valid_registration(self):
        user = UserRegister(
            username="alice", password="x-pw-val", email="alice@test.com"
        )
        assert user.username == "alice"
        assert user.email == "alice@test.com"

    def test_username_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(username="a" * 33, password="x-pw-val", email="long@test.com")
        assert "at most 32" in str(exc_info.value).lower()

    def test_password_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            UserRegister(username="alice", password="a" * 129, email="alice@test.com")
        assert "at most 128" in str(exc_info.value).lower()

    def test_username_min_length(self):
        with pytest.raises(ValidationError):
            UserRegister(username="ab", password="x-pw-val", email="ab@test.com")

    def test_username_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            UserRegister(
                username="user@name", password="x-pw-val", email="user@test.com"
            )

    def test_missing_email_rejected(self):
        with pytest.raises(ValidationError):
            UserRegister(username="alice", password="x-pw-val")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            UserRegister(username="alice", password="x-pw-val", email="not-an-email")


class TestUserLoginValidation:
    """Tests for UserLogin schema validation."""

    def test_valid_login(self):
        login = UserLogin(username="alice", password="x-pw-val")
        assert login.username == "alice"

    def test_empty_username_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UserLogin(username="   ", password="x-pw-val")
        assert "required" in str(exc_info.value).lower()

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UserLogin(username="alice", password="")
        assert "required" in str(exc_info.value).lower()

    def test_username_too_long_rejected(self):
        with pytest.raises(ValidationError):
            UserLogin(username="a" * 33, password="x-pw-val")

    def test_password_too_long_rejected(self):
        with pytest.raises(ValidationError):
            UserLogin(username="alice", password="a" * 129)
