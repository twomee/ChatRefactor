# rate_limit.py — Rate limiting middleware using slowapi
# Enabled only in staging/prod; disabled in dev to avoid interfering with tests
from slowapi import Limiter
from slowapi.util import get_remote_address
from config import REDIS_URL, APP_ENV


def _get_storage_uri():
    """Use Redis for rate limit storage in prod, memory otherwise."""
    if APP_ENV in ("staging", "prod"):
        return REDIS_URL
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_get_storage_uri(),
    default_limits=["100/minute"],
    enabled=APP_ENV in ("staging", "prod"),
)
