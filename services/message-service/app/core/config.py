# app/core/config.py — Message service configuration
#
# Loads .env from the message-service root directory.
# Uses chatbox_messages database — each service owns its own database in the
# microservice architecture.
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

APP_ENV = os.getenv("APP_ENV", "dev")


def _require_env(key: str) -> str:
    """Require an environment variable in production. Fail fast if missing."""
    value = os.getenv(key)
    if value:
        return value
    if APP_ENV == "prod":
        print(
            f"FATAL: Required environment variable '{key}' is not set.", file=sys.stderr
        )
        sys.exit(1)
    return ""


# In dev, generate a random key per process to avoid decoding tokens with an empty string.
_raw_secret = _require_env("SECRET_KEY")
SECRET_KEY = _raw_secret if _raw_secret else secrets.token_urlsafe(64)
ALGORITHM = "HS256"

DATABASE_URL = _require_env("DATABASE_URL")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")

# Redis is optional — used for link preview caching. Empty string means disabled.
REDIS_URL = os.getenv("REDIS_URL", "")
