# app/routers/auth.py — Thin controller for auth endpoints
"""
Public routes: POST /auth/register, /auth/login, /auth/logout, /auth/ping
2FA routes: POST /auth/2fa/setup, /auth/2fa/verify-setup, /auth/2fa/disable,
            /auth/2fa/verify-login, GET /auth/2fa/status
Internal routes: GET /auth/users/{user_id}, /auth/users/by-username/{username}

Key differences from monolith:
1. NO rate limiting decorator — Kong API Gateway handles rate limiting now.
2. NO ConnectionManager injection — presence managed by Chat Service.
3. Internal user lookup endpoints are NEW — used by other services for inter-service calls.
4. Service functions are async (for Kafka event production).
5. 2FA endpoints for TOTP-based two-factor authentication.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user, oauth2_scheme
from app.schemas.auth import (
    ForgotPasswordRequest,
    ProfileResponse,
    ResetPasswordRequest,
    Setup2FAResponse,
    TokenResponse,
    UpdateEmailRequest,
    UpdatePasswordRequest,
    UserLogin,
    UserRegister,
    UserResponse,
    Verify2FARequest,
    VerifyLogin2FARequest,
)
from app.services import auth_service, password_reset_service, two_factor_service
from app.services.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServerError,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("routers.auth")


# ── Public endpoints ──────────────────────────────────────────────────────────


@router.post(
    "/register",
    status_code=201,
    responses={409: {"description": "Username or email already taken"}},
)
async def register(body: UserRegister, db: Annotated[Session, Depends(get_db)]):
    """Register a new user account."""
    try:
        return await auth_service.register(db, body)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc


@router.post(
    "/login",
    responses={401: {"description": "Invalid username or password"}},
)
async def login(body: UserLogin, db: Annotated[Session, Depends(get_db)]):
    """Authenticate and receive a JWT access token.

    If the user has 2FA enabled, returns a Login2FARequiredResponse with a temp_token
    instead of a TokenResponse. The client must then call /auth/2fa/verify-login.
    """
    try:
        return await auth_service.login(db, body)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc


@router.post("/logout", responses={503: {"description": "Logout partially failed"}})
async def logout(
    token: Annotated[str, Depends(oauth2_scheme)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Revoke the current access token (blacklists it in Redis)."""
    try:
        return await auth_service.logout(current_user, token)
    except ServerError as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc


@router.post("/ping")
def ping(current_user: Annotated[dict, Depends(get_current_user)]):
    """Presence ping. In microservice architecture, this is a simple health signal."""
    return auth_service.ping()


# ── Profile / Settings endpoints ──────────────────────────────────────────────


@router.get(
    "/profile",
    response_model=ProfileResponse,
    responses={404: {"description": "User not found"}},
)
def get_profile(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return the authenticated user's profile (username + email)."""
    try:
        return auth_service.get_profile(db, current_user["user_id"])
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


@router.patch(
    "/profile/email",
    responses={
        401: {"description": "Current password is incorrect"},
        404: {"description": "User not found"},
        409: {"description": "Email already registered"},
    },
)
def update_email(
    body: UpdateEmailRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Update the authenticated user's email address. Requires current password."""
    try:
        return auth_service.update_email(
            db, current_user["user_id"], body.new_email, body.current_password
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc


@router.patch(
    "/profile/password",
    responses={
        401: {"description": "Current password is incorrect"},
        404: {"description": "User not found"},
    },
)
def update_password(
    body: UpdatePasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Update the authenticated user's password. Requires current password."""
    try:
        return auth_service.update_password(
            db, current_user["user_id"], body.current_password, body.new_password
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc


# ── Forgot / Reset Password endpoints ────────────────────────────────────────


@router.post("/forgot-password")
def forgot_password(
    body: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Request a password-reset email. Always returns 200 (no email enumeration)."""
    return password_reset_service.request_reset(db, body.email)


@router.post(
    "/reset-password",
    responses={400: {"description": "Invalid or expired reset token"}},
)
def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Reset the user's password using a valid reset token."""
    try:
        return password_reset_service.reset_password(db, body.token, body.new_password)
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


# ── 2FA endpoints ─────────────────────────────────────────────────────────────


@router.post(
    "/2fa/setup",
    response_model=Setup2FAResponse,
    responses={
        400: {"description": "2FA is already enabled"},
        404: {"description": "User not found"},
    },
)
def setup_2fa(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Initiate 2FA setup. Returns a QR code (data URI) and a manual entry key.

    Requires JWT auth. Does NOT enable 2FA — the user must call /2fa/verify-setup
    with a valid TOTP code to confirm they scanned/entered it correctly.
    """
    try:
        return two_factor_service.setup_2fa(db, current_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


@router.post(
    "/2fa/verify-setup",
    responses={
        400: {"description": "Invalid TOTP code or 2FA already enabled"},
        404: {"description": "User not found"},
    },
)
def verify_2fa_setup(
    body: Verify2FARequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Verify a TOTP code to confirm 2FA setup. Enables 2FA on the account."""
    try:
        return two_factor_service.verify_2fa_setup(db, current_user, body.code)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


@router.post(
    "/2fa/disable",
    responses={
        400: {"description": "Invalid TOTP code or 2FA not enabled"},
        404: {"description": "User not found"},
        500: {"description": "Authentication state corrupted"},
    },
)
def disable_2fa(
    body: Verify2FARequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Disable 2FA. Requires a valid TOTP code as proof of ownership."""
    try:
        return two_factor_service.disable_2fa(db, current_user, body.code)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except ServerError as exc:
        raise HTTPException(status_code=500, detail=exc.detail) from exc


@router.post(
    "/2fa/verify-login",
    response_model=TokenResponse,
    responses={401: {"description": "Invalid temp token or TOTP code"}},
)
async def verify_login_2fa(
    body: VerifyLogin2FARequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Complete a 2FA-protected login. Requires temp_token + TOTP code.

    This is a public endpoint (no JWT required) — authentication is via
    the temp_token issued during the login step.
    """
    try:
        return await two_factor_service.verify_login_2fa(db, body.temp_token, body.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc


@router.get("/2fa/status", responses={404: {"description": "User not found"}})
def get_2fa_status(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return the current 2FA status for the authenticated user."""
    try:
        return two_factor_service.get_2fa_status(db, current_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


# ── Internal endpoints (for inter-service communication) ──────────────────────
# NOTE: The by-username route MUST come before the {user_id} route.
# FastAPI matches routes top-to-bottom. If /users/{user_id} is first,
# a request to /users/by-username/alice will match {user_id}="by-username"
# and fail with a type validation error (string can't coerce to int).


@router.get(
    "/users/by-username/{username}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def get_user_by_username(username: str, db: Annotated[Session, Depends(get_db)]):
    """Internal: Look up a user by username. Used by other services."""
    try:
        return auth_service.get_user_by_username(db, username)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def get_user_by_id(user_id: int, db: Annotated[Session, Depends(get_db)]):
    """Internal: Look up a user by ID. Used by other services (Chat, File, etc.)."""
    try:
        return auth_service.get_user_by_id(db, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
