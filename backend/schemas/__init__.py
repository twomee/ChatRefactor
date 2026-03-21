# schemas/__init__.py
import re
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
ROOM_NAME_MAX_LENGTH = 64
MESSAGE_MAX_LENGTH = 5000

# Only allow alphanumeric, underscore, hyphen for usernames
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
# Only allow alphanumeric, spaces, underscore, hyphen for room names
ROOM_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 _-]+$")


class UserRegister(BaseModel):
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
    access_token: str
    token_type: str = "bearer"
    username: str
    is_global_admin: bool

class RoomCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Room name is required")
        if len(v) > ROOM_NAME_MAX_LENGTH:
            raise ValueError(f"Room name must be at most {ROOM_NAME_MAX_LENGTH} characters")
        if not ROOM_NAME_PATTERN.match(v):
            raise ValueError("Room name may only contain letters, numbers, spaces, underscores, and hyphens")
        return v

class RoomResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True

class FileResponse(BaseModel):
    id: int
    original_name: str
    file_size: int
    sender: str
    room_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    message_id: Optional[str] = None
    sender: str
    room_id: Optional[int] = None
    content: str
    is_private: bool
    sent_at: datetime

    class Config:
        from_attributes = True
