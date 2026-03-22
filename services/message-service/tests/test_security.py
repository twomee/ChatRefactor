# tests/test_security.py — Security-focused tests
#
# Covers:
#   - JWT: invalid sub claim type
#   - JWT: token with algorithm confusion prevention
#   - Content truncation on oversized Kafka messages
#   - Input validation on API endpoints
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from app.consumers.persistence_consumer import MAX_CONTENT_LENGTH

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════════
# JWT Security Tests
# ══════════════════════════════════════════════════════════════════════


class TestJWTSecurity:
    """Tests for JWT token validation security."""

    def test_token_with_non_integer_sub_returns_401(self, client):
        """JWT with non-integer 'sub' claim should return 401, not 500."""
        from app.core.config import ALGORITHM, SECRET_KEY

        payload = {
            "sub": "not-an-integer",
            "username": "attacker",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401

    def test_token_without_username_returns_401(self, client):
        """JWT missing 'username' claim should return 401."""
        from app.core.config import ALGORITHM, SECRET_KEY

        payload = {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401

    def test_token_without_sub_returns_401(self, client):
        """JWT missing 'sub' claim should return 401."""
        from app.core.config import ALGORITHM, SECRET_KEY

        payload = {
            "username": "testuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401

    def test_token_signed_with_wrong_key_returns_401(self, client):
        """JWT signed with a different secret should return 401."""
        from app.core.config import ALGORITHM

        payload = {
            "sub": "1",
            "username": "attacker",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/messages/rooms/1/history", headers=headers)
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# Content Length Validation (DoS Prevention)
# ══════════════════════════════════════════════════════════════════════


class TestContentTruncation:
    """Tests for content length limits on Kafka messages."""

    def test_oversized_room_message_is_truncated(self, db, consumer):
        """Room messages exceeding MAX_CONTENT_LENGTH should be truncated."""
        from app.models import Message

        oversized_text = "x" * (MAX_CONTENT_LENGTH + 5000)
        consumer._persist_room_message(
            db,
            {
                "msg_id": "oversized-msg",
                "sender_id": 1,
                "room_id": 1,
                "text": oversized_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        msg = db.query(Message).filter(Message.message_id == "oversized-msg").first()
        assert msg is not None
        assert len(msg.content) == MAX_CONTENT_LENGTH

    def test_normal_message_not_truncated(self, db, consumer):
        """Messages within MAX_CONTENT_LENGTH should not be truncated."""
        from app.models import Message

        normal_text = "Hello, world!"
        consumer._persist_room_message(
            db,
            {
                "msg_id": "normal-msg",
                "sender_id": 1,
                "room_id": 1,
                "text": normal_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        msg = db.query(Message).filter(Message.message_id == "normal-msg").first()
        assert msg is not None
        assert msg.content == normal_text


# ══════════════════════════════════════════════════════════════════════
# API Input Validation
# ══════════════════════════════════════════════════════════════════════


class TestAPIInputValidation:
    """Tests for API parameter validation."""

    def test_negative_room_id_returns_422_or_empty(self, client, auth_headers):
        """Negative room_id should be handled safely (no SQL injection)."""
        response = client.get(
            "/messages/rooms/-1/history", headers=auth_headers
        )
        # Should succeed (just returns empty) since -1 is a valid int
        assert response.status_code == 200
        assert response.json() == []

    def test_limit_exceeding_max_returns_422(self, client, auth_headers):
        """Limit exceeding the maximum should return 422 validation error."""
        response = client.get(
            "/messages/rooms/1?since=2025-01-01T00:00:00&limit=501",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_zero_returns_422(self, client, auth_headers):
        """Limit of 0 should return 422 validation error."""
        response = client.get(
            "/messages/rooms/1?since=2025-01-01T00:00:00&limit=0",
            headers=auth_headers,
        )
        assert response.status_code == 422
