# tests/test_services_auth_service.py — Unit tests for app/services/auth_service.py
"""
Tests for:
- Register with empty username/password (whitespace only)
- Logout with Redis failure (prod mode raises 503, dev mode degrades)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.auth_service import logout, register


class TestRegisterEdgeCases:
    """Tests for register() edge cases."""

    @pytest.mark.asyncio
    async def test_register_whitespace_only_username_returns_400(self):
        """Registering with a username that is only whitespace should fail."""
        mock_db = MagicMock()
        body = MagicMock()
        body.username = MagicMock()
        body.username.strip.return_value = ""
        body.password = MagicMock()
        body.password.strip.return_value = "validpassword"

        with patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await register(mock_db, body)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_whitespace_only_password_returns_400(self):
        """Registering with a password that is only whitespace should fail."""
        mock_db = MagicMock()
        body = MagicMock()
        body.username = MagicMock()
        body.username.strip.return_value = "validuser"
        body.password = MagicMock()
        body.password.strip.return_value = ""

        with patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await register(mock_db, body)
            assert exc_info.value.status_code == 400


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
    async def test_logout_redis_failure_in_dev_degrades(self):
        """In dev mode, if Redis is down during logout, should succeed but log error."""
        user_info = {"user_id": 1, "username": "bob"}

        with patch("app.services.auth_service.APP_ENV", "dev"), \
             patch("app.infrastructure.redis.get_redis", side_effect=Exception("Redis down")), \
             patch("app.services.auth_service.produce_event", new_callable=AsyncMock):
            result = await logout(user_info, "fake-token")
            assert result["message"] == "Logged out"
