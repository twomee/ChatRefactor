# config.py
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (one level up from backend/)
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

APP_ENV = os.getenv("APP_ENV", "dev")
BASE_DIR = Path(__file__).parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/chatbox.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "24"))
MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if o.strip()
]

# Admin credentials — set these via environment variables in production
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ido")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {
    ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".mp4", ".mp3", ".wav", ".ogg",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".py", ".js", ".ts", ".html", ".css", ".json", ".md",
    ".bin", ".dat", ".csv", ".xml", ".yaml", ".yml", ".log",
}
