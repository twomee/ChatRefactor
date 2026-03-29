# app/infrastructure/redis_client.py — Async Redis client for the message service
#
# Used for caching link previews. Redis is optional — if unavailable, the service
# degrades gracefully (no caching, every preview is fetched fresh).
#
# The client is initialized during app lifespan startup and closed on shutdown.
import redis.asyncio as redis

from app.core.config import REDIS_URL
from app.core.logging import get_logger

logger = get_logger("infrastructure.redis")

# Module-level singleton — set during lifespan startup
_client: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize the async Redis connection pool.

    Called during app lifespan startup. If REDIS_URL is not configured,
    Redis is silently skipped (link preview caching will be disabled).
    """
    global _client
    if not REDIS_URL:
        logger.info("redis_disabled", msg="REDIS_URL not configured — preview caching disabled")
        return
    try:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
        await _client.ping()
        logger.info("redis_connected", url=REDIS_URL.split("@")[-1] if "@" in REDIS_URL else "***")
    except Exception as exc:
        logger.warning("redis_connection_failed", error=str(exc))
        _client = None


async def close_redis() -> None:
    """Close the Redis connection pool. Called during app lifespan shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis_disconnected")


def get_redis() -> redis.Redis | None:
    """Return the current Redis client, or None if not connected."""
    return _client
