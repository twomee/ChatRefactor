# redis_client.py — Redis connection pool (singleton)
import redis
from config import REDIS_URL

redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)


def get_redis() -> redis.Redis:
    """Return a Redis client from the shared connection pool."""
    return redis.Redis(connection_pool=redis_pool)
