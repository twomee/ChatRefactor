# tests/test_services_auth_service.py — Unit tests for app/services/auth_service.py
"""
Tests for:
- Register duplicate username (race condition returns 409)
- Register concurrent IntegrityError returns 409 instead of 500
- Logout with Redis failure (prod mode raises 503, dev/staging mode degrades)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.services.auth_service import logout, register


class TestRegisterEdgeCases:
    """Tests for register() edge cases."""

    @pytest.mark.asyncio
    async def test_register_duplicate_username_returns_409(self):
        """Registering with an existing username should return 409."""
        mock_db = MagicMock()
        body = MagicMock()
        body.username = "existinguser"
        body.password = "x-pw-val"
        body.email = "existing@test.com"

        with patch("app.services.auth_service.user_dal") as mock_dal, \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            mock_dal.get_by_username.return_value = MagicMock()  # user exists
            with pytest.raises(HTTPException) as exc_info:
                await register(mock_db, body)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_register_concurrent_duplicate_returns_409_not_500(self):
        """Race condition: IntegrityError on concurrent duplicate should return 409."""
        mock_db = MagicMock()
        body = MagicMock()
        body.username = "newuser"
        body.password = "x-pw-val"
        body.email = "new@test.com"

        with patch("app.services.auth_service.user_dal") as mock_dal, \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock), \
             patch("app.services.auth_service.hash_password", return_value="hashed"):
            mock_dal.get_by_username.return_value = None  # passes check
            mock_dal.get_by_email.return_value = None  # passes email check
            mock_dal.create.side_effect = IntegrityError(
                "duplicate", {}, Exception("unique constraint")
            )
            with pytest.raises(HTTPException) as exc_info:
                await register(mock_db, body)
            assert exc_info.value.status_code == 409
            mock_db.rollback.assert_called_once()


class TestLogoutRedisFailure:
    """Tests for logout() when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_logout_redis_failure_in_prod_raises_503(self):
        """In production, if Redis is down during logout, return 503."""
        user_info = {"user_id": 1, "username": "alice"}

        with patch("app.services.auth_service.APP_ENV", "prod"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")), \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await logout(user_info, "fake-token")
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_logout_redis_failure_in_staging_raises_503(self):
        """In staging, if Redis is down during logout, return 503 (fail closed)."""
        user_info = {"user_id": 1, "username": "carol"}

        with patch("app.services.auth_service.APP_ENV", "staging"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")), \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await logout(user_info, "fake-token")
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_logout_redis_failure_in_dev_degrades(self):
        """In dev mode, if Redis is down during logout, should succeed but log error."""
        user_info = {"user_id": 1, "username": "bob"}

        with patch("app.services.auth_service.APP_ENV", "dev"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")), \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            result = await logout(user_info, "fake-token")
            assert result["message"] == "Logged out"
