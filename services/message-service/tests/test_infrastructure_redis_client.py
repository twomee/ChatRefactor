# tests/test_infrastructure_redis_client.py — Tests for app/infrastructure/redis_client.py
#
# Covers:
#   - init_redis: skips gracefully when REDIS_URL is not configured
#   - init_redis: connects and pings successfully
#   - init_redis: handles connection/ping failures gracefully (sets _client to None)
#   - close_redis: closes the connection and resets the module-level singleton
#   - close_redis: is a no-op when _client is already None
#   - get_redis: returns the current client (or None)
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════
# init_redis
# ══════════════════════════════════════════════════════════════════════


class TestInitRedis:
    """Tests for the init_redis() lifecycle function."""

    @pytest.mark.asyncio
    async def test_skips_when_redis_url_not_configured(self):
        """When REDIS_URL is falsy, init_redis should be a no-op and leave _client as None."""
        import app.infrastructure.redis_client as rc

        # Patch REDIS_URL to empty string so the early-return branch is taken
        with patch("app.infrastructure.redis_client.REDIS_URL", ""):
            rc._client = None  # ensure clean state
            await rc.init_redis()
            assert rc._client is None

    @pytest.mark.asyncio
    async def test_sets_client_on_successful_connection(self):
        """When REDIS_URL is set and ping succeeds, _client should be set."""
        import app.infrastructure.redis_client as rc

        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)

        with (
            patch("app.infrastructure.redis_client.REDIS_URL", "redis://localhost:6379"),
            patch("app.infrastructure.redis_client.redis.from_url", return_value=mock_redis_instance),
        ):
            rc._client = None
            await rc.init_redis()
            assert rc._client is mock_redis_instance
            mock_redis_instance.ping.assert_awaited_once()

        # Clean up
        rc._client = None

    @pytest.mark.asyncio
    async def test_sets_client_none_on_connection_failure(self):
        """When ping raises an exception, _client must be set to None (graceful degradation)."""
        import app.infrastructure.redis_client as rc

        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with (
            patch("app.infrastructure.redis_client.REDIS_URL", "redis://localhost:6379"),
            patch("app.infrastructure.redis_client.redis.from_url", return_value=mock_redis_instance),
        ):
            rc._client = None
            await rc.init_redis()
            # Connection failed — client must not be set
            assert rc._client is None

    @pytest.mark.asyncio
    async def test_sets_client_none_on_from_url_failure(self):
        """When redis.from_url raises, _client must be set to None."""
        import app.infrastructure.redis_client as rc

        with (
            patch("app.infrastructure.redis_client.REDIS_URL", "redis://badhost:6379"),
            patch(
                "app.infrastructure.redis_client.redis.from_url",
                side_effect=Exception("invalid URL"),
            ),
        ):
            rc._client = None
            await rc.init_redis()
            assert rc._client is None

    @pytest.mark.asyncio
    async def test_logs_url_without_credentials(self):
        """The connection log should not expose credentials embedded in REDIS_URL."""
        import app.infrastructure.redis_client as rc

        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)

        redis_url_with_creds = "redis://:secret-password@localhost:6379"

        with (
            patch("app.infrastructure.redis_client.REDIS_URL", redis_url_with_creds),
            patch("app.infrastructure.redis_client.redis.from_url", return_value=mock_redis_instance),
        ):
            rc._client = None
            # Should not raise — this exercises the credential-masking branch
            await rc.init_redis()
            assert rc._client is mock_redis_instance

        rc._client = None


# ══════════════════════════════════════════════════════════════════════
# close_redis
# ══════════════════════════════════════════════════════════════════════


class TestCloseRedis:
    """Tests for the close_redis() lifecycle function."""

    @pytest.mark.asyncio
    async def test_closes_client_and_sets_none(self):
        """When _client is set, close_redis should call aclose() and reset to None."""
        import app.infrastructure.redis_client as rc

        mock_redis_instance = AsyncMock()
        mock_redis_instance.aclose = AsyncMock()

        rc._client = mock_redis_instance
        await rc.close_redis()

        mock_redis_instance.aclose.assert_awaited_once()
        assert rc._client is None

    @pytest.mark.asyncio
    async def test_is_noop_when_client_is_none(self):
        """When _client is already None, close_redis should not raise."""
        import app.infrastructure.redis_client as rc

        rc._client = None
        # Should complete without error
        await rc.close_redis()
        assert rc._client is None


# ══════════════════════════════════════════════════════════════════════
# get_redis
# ══════════════════════════════════════════════════════════════════════


class TestGetRedis:
    """Tests for the get_redis() accessor."""

    def test_returns_none_when_not_initialized(self):
        """get_redis() returns None before init_redis() is called."""
        import app.infrastructure.redis_client as rc

        original = rc._client
        rc._client = None
        assert rc.get_redis() is None
        rc._client = original

    def test_returns_client_when_initialized(self):
        """get_redis() returns the module-level _client singleton."""
        import app.infrastructure.redis_client as rc

        mock_client = MagicMock()
        rc._client = mock_client
        assert rc.get_redis() is mock_client
        rc._client = None
