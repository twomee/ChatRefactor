# tests/test_core_security.py — Tests for app/core/security.py
#
# Covers:
#   - decode_token: valid token, expired token, missing claims, wrong key
#   - get_current_user: valid payload, non-integer sub, missing sub, missing username
from datetime import datetime, timedelta, timezone

import pytest
import jwt

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.security import decode_token, get_current_user


# ══════════════════════════════════════════════════════════════════════
# decode_token
# ══════════════════════════════════════════════════════════════════════


class TestDecodeToken:
    """Tests for the decode_token function."""

    def test_valid_token_returns_user_info(self):
        """Should return a dict with user_id and username for a valid token."""
        payload = {
            "sub": "1",
            "username": "testuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(token)

        assert result is not None
        assert result["user_id"] == 1
        assert result["username"] == "testuser"

    def test_expired_token_returns_none(self):
        """Should return None for an expired token."""
        payload = {
            "sub": "1",
            "username": "testuser",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(token)

        assert result is None

    def test_missing_sub_returns_none(self):
        """Should return None when 'sub' claim is missing."""
        payload = {
            "username": "testuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(token)

        assert result is None

    def test_missing_username_returns_none(self):
        """Should return None when 'username' claim is missing."""
        payload = {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(token)

        assert result is None

    def test_wrong_secret_key_returns_none(self):
        """Should return None when token is signed with a different key."""
        payload = {
            "sub": "1",
            "username": "testuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)

        result = decode_token(token)

        assert result is None

    def test_malformed_token_returns_none(self):
        """Should return None for a malformed token string."""
        result = decode_token("not-a-valid-jwt")

        assert result is None


# ══════════════════════════════════════════════════════════════════════
# get_current_user
# ══════════════════════════════════════════════════════════════════════


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    def test_valid_token_returns_user_dict(self):
        """Should return a dict with user_id and username for a valid token."""
        payload = {
            "sub": "42",
            "username": "alice",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        result = get_current_user(token)

        assert result == {"user_id": 42, "username": "alice"}

    def test_non_integer_sub_raises_401(self):
        """JWT with non-integer 'sub' should raise HTTPException 401."""
        from fastapi import HTTPException

        payload = {
            "sub": "not-an-integer",
            "username": "attacker",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token)

        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """Expired token should raise HTTPException 401."""
        from fastapi import HTTPException

        payload = {
            "sub": "1",
            "username": "testuser",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token)

        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        """Malformed token should raise HTTPException 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_current_user("not-a-valid-jwt")

        assert exc_info.value.status_code == 401

    def test_token_without_sub_raises_401(self, client):
        """JWT missing 'sub' claim should return 401 via the endpoint."""
        payload = {
            "username": "testuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401

    def test_token_without_username_raises_401(self, client):
        """JWT missing 'username' claim should return 401 via the endpoint."""
        payload = {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401

    def test_token_signed_with_wrong_key_returns_401(self, client):
        """JWT signed with a different secret should return 401 via the endpoint."""
        payload = {
            "sub": "1",
            "username": "attacker",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401
