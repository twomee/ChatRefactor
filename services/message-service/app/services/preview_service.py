# app/services/preview_service.py — Link preview orchestration service
#
# Coordinates Redis caching with URL preview fetching. Keeps the router
# thin by encapsulating the cache-check → fetch → cache-store flow.
from app.infrastructure.redis_client import get_redis
from app.services.url_preview_service import (
    cache_preview,
    fetch_preview,
    get_cached_preview,
)


async def get_link_preview(url: str) -> dict | None:
    """Fetch link preview with Redis caching. Returns None if preview unavailable."""
    redis_client = get_redis()

    cached = await get_cached_preview(redis_client, url)
    if cached is not None:
        if cached.get("_miss"):
            return None
        return cached

    preview = await fetch_preview(url)
    await cache_preview(redis_client, url, preview)
    return preview
