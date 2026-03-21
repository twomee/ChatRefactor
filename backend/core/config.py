# core/config.py
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (one level up from backend/)
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

APP_ENV = os.getenv("APP_ENV", "dev")
BASE_DIR = Path(__file__).parent.parent


def _require_env(key: str) -> str:
    """Require an environment variable in production. Fail fast if missing."""
    value = os.getenv(key)
    if not value and APP_ENV == "prod":
        print(f"FATAL: Required environment variable '{key}' is not set.", file=sys.stderr)
        sys.exit(1)
    return value or ""


# --- Security-sensitive settings (no hardcoded defaults) ---
SECRET_KEY = _require_env("SECRET_KEY")
DATABASE_URL = _require_env("DATABASE_URL")
ADMIN_USERNAME = _require_env("ADMIN_USERNAME")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "24"))
MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# --- Infrastructure (safe defaults for local dev) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if o.strip()
]

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mp3",
    ".wav",
    ".ogg",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".json",
    ".md",
    ".bin",
    ".dat",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
}
