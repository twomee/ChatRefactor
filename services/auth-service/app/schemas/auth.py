# app/schemas/auth.py — Pydantic request/response schemas for auth endpoints
"""
Ported from monolith schemas. Only auth-relevant schemas are included.
Room, File, and Message schemas belong to their respective services.
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    email: EmailStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < USERNAME_MIN_LENGTH:
            raise ValueError(
                f"Username must be at least {USERNAME_MIN_LENGTH} characters"
            )
        if len(v) > USERNAME_MAX_LENGTH:
            raise ValueError(
                f"Username must be at most {USERNAME_MAX_LENGTH} characters"
            )
        if not USERNAME_PATTERN.match(v):
            raise ValueError(
                "Username may only contain letters, numbers, underscores, and hyphens"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
            )
        if len(v) > PASSWORD_MAX_LENGTH:
            raise ValueError(
                f"Password must be at most {PASSWORD_MAX_LENGTH} characters"
            )
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
    user_id: int


class UserResponse(BaseModel):
    """Schema for internal user lookup responses (used by other services)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    is_global_admin: bool
    created_at: datetime


# ── Two-Factor Authentication Schemas ────────────────────────────────────


class Setup2FAResponse(BaseModel):
    """Response when initiating 2FA setup.

    qr_code: data URI (PNG) for the QR code — scan with any TOTP app (Google Authenticator, Authy).
    manual_entry_key: raw base32 secret for apps that can't scan QR codes.
    Note: the raw otpauth:// URI is intentionally not returned; QR code is generated server-side.
    """

    qr_code: str  # data:image/png;base64,... — ready to render as <img src=...>
    manual_entry_key: str  # base32 TOTP secret for manual authenticator entry


class Verify2FARequest(BaseModel):
    """Request to verify a TOTP code (used for setup confirmation and disabling)."""

    code: str = Field(..., min_length=6, max_length=6)


class Login2FARequiredResponse(BaseModel):
    """Response when login succeeds but 2FA verification is still needed."""

    requires_2fa: bool = True
    temp_token: str  # short-lived token for the 2FA verification step
    message: str = "2FA verification required"


class VerifyLogin2FARequest(BaseModel):
    """Request to complete login with a TOTP code after receiving a temp_token."""

    temp_token: str
    code: str = Field(..., min_length=6, max_length=6)


# ── Profile / Settings Schemas ────────────────────────────────────────


class UpdateEmailRequest(BaseModel):
    """Request to change the user's email address. Requires current password."""

    new_email: EmailStr
    current_password: str


class UpdatePasswordRequest(BaseModel):
    """Request to change the user's password. Requires current password."""

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class ProfileResponse(BaseModel):
    """Response for the authenticated user's profile."""

    username: str
    email: str | None = None


# ── Forgot / Reset Password Schemas ──────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    """Request to initiate a password-reset flow."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request to set a new password using a reset token."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
