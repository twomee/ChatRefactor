# tests/test_security.py — Unit tests for security module (JWT, passwords, dependencies)
"""
Tests for:
- decode_token with Redis failure (prod vs dev)
- decode_token with missing 'sub' claim
- require_admin dependency (always raises 403)
- hash_password / verify_password edge cases
- create_access_token / decode_token round-trip
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)


# ── Password hashing ─────────────────────────────────────────────────


class TestPasswordHashing:
    """Tests for hash_password and verify_password."""

    def test_hash_and_verify_correct_password(self):
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed) is True

    def test_verify_wrong_password_returns_false(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_hash_produces_different_hashes_for_same_password(self):
        """Argon2 uses random salt, so same password should produce different hashes."""
        hash1 = hash_password("password")
        hash2 = hash_password("password")
        assert hash1 != hash2


# ── Token creation and decoding ───────────────────────────────────────


class TestTokens:
    """Tests for create_access_token and decode_token."""

    def test_create_and_decode_round_trip(self):
        """Created token should decode back to the original claims."""
        token = create_access_token({"sub": "42", "username": "alice"})

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.infrastructure.redis.get_redis", return_value=mock_redis):
            result = decode_token(token)

        assert result is not None
        assert result["user_id"] == 42
        assert result["username"] == "alice"

    def test_decode_invalid_token_returns_none(self):
        result = decode_token("not.a.valid.token")
        assert result is None

    def test_decode_expired_token_returns_none(self):
        """An expired token should return None."""
        from datetime import datetime, timedelta, timezone
        import jwt as pyjwt
        from app.core.config import ALGORITHM, SECRET_KEY

        expired_payload = {
            "sub": "1",
            "username": "bob",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = pyjwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        result = decode_token(expired_token)
        assert result is None

    def test_decode_token_missing_sub_returns_none(self):
        """A token without a 'sub' claim should return None."""
        token = create_access_token({"username": "nosub"})

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.infrastructure.redis.get_redis", return_value=mock_redis):
            result = decode_token(token)

        assert result is None

    def test_decode_blacklisted_token_returns_none(self):
        """A blacklisted token should return None."""
        token = create_access_token({"sub": "1", "username": "blacklisted"})

        mock_redis = MagicMock()
        mock_redis.get.return_value = "1"  # token is blacklisted

        with patch("app.infrastructure.redis.get_redis", return_value=mock_redis):
            result = decode_token(token)

        assert result is None


# ── Redis failure in decode_token ─────────────────────────────────────


class TestDecodeTokenRedisFailure:
    """Tests for decode_token when Redis is unavailable."""

    def test_redis_failure_in_prod_rejects_token(self):
        """In production, if Redis is down, token should be rejected (fail closed)."""
        token = create_access_token({"sub": "1", "username": "alice"})

        with patch("app.core.security.APP_ENV", "prod"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")):
            result = decode_token(token)

        assert result is None

    def test_redis_failure_in_dev_allows_token(self):
        """In dev mode, if Redis is down, token should still be accepted (fail open)."""
        token = create_access_token({"sub": "1", "username": "alice"})

        with patch("app.core.security.APP_ENV", "dev"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")):
            result = decode_token(token)

        assert result is not None
        assert result["user_id"] == 1
        assert result["username"] == "alice"

    def test_redis_failure_in_staging_allows_token(self):
        """In staging mode, if Redis is down, token should still be accepted."""
        token = create_access_token({"sub": "1", "username": "alice"})

        with patch("app.core.security.APP_ENV", "staging"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")):
            result = decode_token(token)

        assert result is not None


# ── get_current_user ──────────────────────────────────────────────────


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    def test_valid_token_returns_user_info(self):
        token = create_access_token({"sub": "5", "username": "testuser"})

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.infrastructure.redis.get_redis", return_value=mock_redis):
            result = get_current_user(token)

        assert result["user_id"] == 5
        assert result["username"] == "testuser"

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user("invalid-token")
        assert exc_info.value.status_code == 401


# ── require_admin ─────────────────────────────────────────────────────


class TestRequireAdmin:
    """Tests for the require_admin dependency."""

    def test_require_admin_always_raises_403(self):
        """The require_admin dependency always raises 403 (by design)."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin({"user_id": 1, "username": "admin"})
        assert exc_info.value.status_code == 403
