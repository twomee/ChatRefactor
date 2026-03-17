# config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATABASE_URL = f"sqlite:///{BASE_DIR}/chatbox.db"
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Admin credentials — set these via environment variables in production
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ido")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
