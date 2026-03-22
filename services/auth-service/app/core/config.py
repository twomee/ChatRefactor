# app/core/config.py — Auth service configuration
"""
Auth-relevant settings only. File/CORS/upload settings live in their respective services.
Loads .env from the auth-service root directory (not the project root).

Uses chatbox_auth database (not chatbox) — each service owns its own database in the
microservice architecture.
"""

import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from auth-service root (two levels up from this file: app/core/ -> app/ -> auth-service/)
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

APP_ENV = os.getenv("APP_ENV", "dev")


def _require_env(key: str) -> str:
    """Require an environment variable in production. Fail fast if missing."""
    value = os.getenv(key)
    if not value and APP_ENV == "prod":
        print(
            f"FATAL: Required environment variable '{key}' is not set.", file=sys.stderr
        )
        sys.exit(1)
    return value or ""


# --- Security-sensitive settings (no hardcoded defaults) ---
# In prod, SECRET_KEY is required via _require_env (sys.exit if missing).
# In dev, generate a random key per process to avoid signing tokens with an empty string.
_raw_secret = _require_env("SECRET_KEY")
SECRET_KEY = _raw_secret if _raw_secret else secrets.token_urlsafe(64)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chatbox:chatbox_pass@localhost:5432/chatbox_auth",
)
if not DATABASE_URL and APP_ENV == "prod":
    print(
        "FATAL: Required environment variable 'DATABASE_URL' is not set.",
        file=sys.stderr,
    )
    sys.exit(1)

ADMIN_USERNAME = _require_env("ADMIN_USERNAME")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "24"))

# --- Infrastructure (safe defaults for local dev) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
