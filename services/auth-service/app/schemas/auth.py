# app/schemas/auth.py — Pydantic request/response schemas for auth endpoints
"""
Ported from monolith schemas. Only auth-relevant schemas are included.
Room, File, and Message schemas belong to their respective services.
"""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

# ── Constants ─────────────────────────────────────────────────────────
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Only allow alphanumeric, underscore, hyphen for usernames
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class UserRegister(BaseModel):
    """Schema for user registration requests."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < USERNAME_MIN_LENGTH:
            raise ValueError(f"Username must be at least {USERNAME_MIN_LENGTH} characters")
        if len(v) > USERNAME_MAX_LENGTH:
            raise ValueError(f"Username must be at most {USERNAME_MAX_LENGTH} characters")
        if not USERNAME_PATTERN.match(v):
            raise ValueError("Username may only contain letters, numbers, underscores, and hyphens")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
        if len(v) > PASSWORD_MAX_LENGTH:
            raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters")
        return v


class UserLogin(BaseModel):
    """Schema for user login requests."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Username is required")
        if len(v) > USERNAME_MAX_LENGTH:
            raise ValueError("Invalid username")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError("Password is required")
        if len(v) > PASSWORD_MAX_LENGTH:
            raise ValueError("Invalid password")
        return v


class TokenResponse(BaseModel):
    """Schema for login response — returns JWT + user metadata."""

    access_token: str
    token_type: str = "bearer"
    username: str
    is_global_admin: bool


class UserResponse(BaseModel):
    """Schema for internal user lookup responses (used by other services)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_global_admin: bool
    created_at: datetime
