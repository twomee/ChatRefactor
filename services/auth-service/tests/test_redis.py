# tests/test_redis.py — Unit tests for Redis infrastructure module
"""
Tests for:
- get_redis returns a Redis client from the pool
"""
from unittest.mock import MagicMock, patch


class TestGetRedis:
    """Tests for get_redis()."""

    def test_get_redis_returns_redis_client(self):
        """get_redis should return a redis.Redis instance from the connection pool."""
        mock_pool = MagicMock()

        with patch("app.infrastructure.redis.redis_pool", mock_pool):
            from app.infrastructure.redis import get_redis

            client = get_redis()
            # Verify it returned something (the actual Redis constructor is called
            # with the mock pool)
            assert client is not None
