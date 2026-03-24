# app/core/config.py — Message service configuration
#
# Loads .env from the message-service root directory.
# Uses chatbox_messages database — each service owns its own database in the
# microservice architecture.
import os
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


SECRET_KEY = _require_env("SECRET_KEY")
ALGORITHM = "HS256"

DATABASE_URL = _require_env("DATABASE_URL")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
