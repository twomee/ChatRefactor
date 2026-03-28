# app/infrastructure/redis.py — Redis connection pool (singleton)
import redis

from app.core.config import REDIS_URL

redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=3,
    socket_connect_timeout=3,
    retry_on_timeout=True,
)


def get_redis() -> redis.Redis:
    """Return a Redis client from the shared connection pool."""
    return redis.Redis(connection_pool=redis_pool)


def close_redis_pool():
    """Disconnect all Redis connections. Called on shutdown."""
    redis_pool.disconnect()
