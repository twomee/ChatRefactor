# app/models/__init__.py — User model only (auth service owns user identity)
"""
This service only contains the User model. Room, Message, File, and other
domain models belong to their respective services.
No relationships are defined — those models don't exist in this bounded context.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_global_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Two-Factor Authentication (TOTP) ─────────────────────────────
    totp_secret = Column(String(256), nullable=True)  # Encrypted with AES-256-GCM
    is_2fa_enabled = Column(Boolean, default=False, nullable=False)
    backup_codes = Column(Text, nullable=True)  # JSON array of hashed codes
