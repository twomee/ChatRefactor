# app/services/auth_service.py — Business logic for registration, login, logout, ping, 2FA
"""
Key differences from monolith:
1. NO ConnectionManager dependency — auth service doesn't manage WebSocket presence.
   Presence is handled by the Chat Service, which consumes auth.events from Kafka.
2. Produces Kafka events (fire-and-forget) for user_registered, user_logged_in, user_logged_out.
3. ping simply returns ok — no presence management needed.
4. 2FA (TOTP) support: setup, verify-setup, disable, and verify-login flows.
"""

import secrets

import pyotp
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ACCESS_TOKEN_EXPIRE_HOURS, APP_ENV
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.dal import user_dal
from app.infrastructure.kafka_producer import produce_event
from app.infrastructure.metrics import (
    auth_2fa_operations_total,
    auth_logins_total,
    auth_logouts_total,
    auth_registrations_total,
)
from app.schemas.auth import TokenResponse, UserLogin, UserRegister

logger = get_logger("services.auth")


async def register(db: Session, body: UserRegister) -> dict:
    """Register a new user.

    Flow: check duplicate -> hash password -> persist -> produce event.
    Input validation (username format, password length) is handled by the
    Pydantic schema (UserRegister) before this function is called.
    The Kafka event is fire-and-forget: registration succeeds even if Kafka is down.
    """
    if user_dal.get_by_username(db, body.username):
        auth_registrations_total.labels(status="duplicate").inc()
        raise HTTPException(status_code=409, detail="Username already taken")

    try:
        user = user_dal.create(
            db, username=body.username, password_hash=hash_password(body.password)
        )
    except IntegrityError:
        db.rollback()
        auth_registrations_total.labels(status="duplicate").inc()
        raise HTTPException(status_code=409, detail="Username already taken")

    logger.info("user_registered", username=user.username, user_id=user.id)
    auth_registrations_total.labels(status="success").inc()

    # Fire-and-forget Kafka event — don't fail registration if Kafka is down
    await produce_event(
        "user_registered", {"user_id": user.id, "username": user.username}
    )

    return {"message": "Registered successfully"}


_DUMMY_HASH = hash_password("timing-equalization-dummy")


async def login(db: Session, body: UserLogin) -> TokenResponse | dict:
    """Authenticate a user and return a JWT token (or a 2FA challenge).

    Flow: find user -> verify password -> check 2FA -> create JWT or temp_token.
    Always runs password verification to prevent timing-based username enumeration.

    If the user has 2FA enabled, returns a Login2FARequiredResponse dict instead of a
    TokenResponse. The frontend must then call /auth/2fa/verify-login with the temp_token
    and a valid TOTP code to complete the login.
    """
    user = user_dal.get_by_username(db, body.username)
    if not user:
        # Equalize timing: run Argon2 verification even when user doesn't exist
        # to prevent attackers from distinguishing "user not found" (fast) vs
        # "wrong password" (slow due to Argon2)
        verify_password(body.password, _DUMMY_HASH)
        logger.warning("login_failed", username=body.username)
        auth_logins_total.labels(status="invalid_credentials").inc()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(body.password, user.password_hash):
        logger.warning("login_failed", username=body.username)
        auth_logins_total.labels(status="invalid_credentials").inc()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # ── 2FA gate: if enabled, issue a short-lived temp_token instead of a JWT ──
    if user.is_2fa_enabled:
        temp_token = _store_2fa_temp_token(user.id, user.username)
        logger.info("2fa_challenge_issued", username=user.username, user_id=user.id)
        auth_logins_total.labels(status="2fa_required").inc()
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "2FA verification required",
        }

    token = create_access_token({"sub": str(user.id), "username": user.username})
    logger.info("user_logged_in", username=user.username, user_id=user.id)
    auth_logins_total.labels(status="success").inc()

    # Fire-and-forget Kafka event
    await produce_event(
        "user_logged_in", {"user_id": user.id, "username": user.username}
    )

    return TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )


async def logout(user_info: dict, token: str) -> dict:
    """Log out a user by blacklisting their token in Redis.

    Flow: blacklist token -> produce event -> return message.
    If Redis is down in production or staging, return 503 (token can't be revoked).
    In dev, degrades gracefully (logs error, returns success with degraded metric).
    """
    username = user_info["username"]
    user_id = user_info["user_id"]

    # Blacklist the token in Redis so it can't be reused
    blacklist_ok = False
    try:
        from app.infrastructure.redis import get_redis

        r = get_redis()
        r.setex(f"blacklist:{token}", ACCESS_TOKEN_EXPIRE_HOURS * 3600, "1")
        blacklist_ok = True
    except Exception as exc:
        logger.error(
            "token_blacklist_failed",
            username=username,
            msg="Redis unavailable — token cannot be revoked until expiry",
        )
        if APP_ENV in ("prod", "staging"):
            raise HTTPException(
                status_code=503,
                detail="Logout partially failed — please try again or change your password",
            ) from exc

    logger.info("user_logged_out", username=username, user_id=user_id)
    auth_logouts_total.labels(status="success" if blacklist_ok else "degraded").inc()

    # Fire-and-forget Kafka event
    await produce_event("user_logged_out", {"user_id": user_id, "username": username})

    return {"message": "Logged out"}


def ping() -> dict:
    """Simple presence ping. Returns ok.

    In the microservice architecture, presence is managed by the Chat Service.
    The auth service's ping is a simple health signal — no ConnectionManager calls.
    """
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
#  Two-Factor Authentication (TOTP)
# ═══════════════════════════════════════════════════════════════════════════

_2FA_TEMP_TOKEN_TTL = 300  # 5 minutes
_2FA_TEMP_TOKEN_PREFIX = "2fa_temp:"


def _get_redis():
    """Lazy import to avoid circular import at module level."""
    from app.infrastructure.redis import get_redis

    return get_redis()


def _store_2fa_temp_token(user_id: int, username: str) -> str:
    """Generate a cryptographic temp token and store it in Redis with a 5-min TTL.

    The token maps to the user_id + username so we can issue a real JWT after
    the TOTP code is verified without re-authenticating the password.
    """
    import json

    token = secrets.token_urlsafe(48)
    payload = json.dumps({"user_id": user_id, "username": username})
    _get_redis().setex(
        f"{_2FA_TEMP_TOKEN_PREFIX}{token}", _2FA_TEMP_TOKEN_TTL, payload
    )
    return token


def _consume_2fa_temp_token(token: str) -> dict | None:
    """Retrieve and delete a 2FA temp token from Redis (single-use).

    Returns the stored user info dict or None if the token is expired/invalid.
    """
    import json

    r = _get_redis()
    key = f"{_2FA_TEMP_TOKEN_PREFIX}{token}"
    raw = r.get(key)
    if raw is None:
        return None
    r.delete(key)  # single-use: consume immediately
    return json.loads(raw)


# ── TOTP helpers ─────────────────────────────────────────────────────────


def generate_totp_secret() -> str:
    """Generate a random base32-encoded TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Build an otpauth:// URI suitable for QR code generation."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="cHATBOX")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against the secret, allowing +/- 1 period tolerance."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ── 2FA service functions ────────────────────────────────────────────────


def setup_2fa(db: Session, user_info: dict) -> dict:
    """Generate a TOTP secret and store it (not yet enabled).

    Returns the secret and otpauth URI so the frontend can show a QR code.
    The user must call verify-setup with a valid code to actually enable 2FA.
    """
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    secret = generate_totp_secret()
    user_dal.update_2fa_secret(db, user.id, secret)

    uri = get_totp_uri(secret, user.username)
    logger.info("2fa_setup_initiated", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(operation="setup", status="initiated").inc()

    return {"secret": secret, "otpauth_uri": uri}


def verify_2fa_setup(db: Session, user_info: dict, code: str) -> dict:
    """Confirm 2FA setup by verifying a TOTP code, then enable 2FA on the account."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /auth/2fa/setup first")

    if not verify_totp(user.totp_secret, code):
        logger.warning(
            "2fa_setup_verification_failed",
            username=user.username,
            user_id=user.id,
        )
        auth_2fa_operations_total.labels(
            operation="verify_setup", status="invalid_code"
        ).inc()
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    user_dal.enable_2fa(db, user.id)
    logger.info("2fa_enabled", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(
        operation="verify_setup", status="success"
    ).inc()

    return {"message": "2FA enabled successfully"}


def disable_2fa(db: Session, user_info: dict, code: str) -> dict:
    """Disable 2FA after verifying a TOTP code (proof that the user owns the secret)."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not verify_totp(user.totp_secret, code):
        logger.warning(
            "2fa_disable_failed", username=user.username, user_id=user.id
        )
        auth_2fa_operations_total.labels(
            operation="disable", status="invalid_code"
        ).inc()
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    user_dal.disable_2fa(db, user.id)
    logger.info("2fa_disabled", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(operation="disable", status="success").inc()

    return {"message": "2FA disabled successfully"}


async def verify_login_2fa(db: Session, temp_token: str, code: str) -> TokenResponse:
    """Complete a 2FA-protected login by verifying the temp_token + TOTP code.

    Consumes the single-use temp_token from Redis, verifies the TOTP code, and
    returns a full JWT if both are valid.
    """
    user_data = _consume_2fa_temp_token(temp_token)
    if user_data is None:
        auth_2fa_operations_total.labels(
            operation="verify_login", status="expired_token"
        ).inc()
        raise HTTPException(
            status_code=401, detail="Temp token expired or invalid — please log in again"
        )

    user = user_dal.get_by_id(db, user_data["user_id"])
    if not user or not user.is_2fa_enabled or not user.totp_secret:
        auth_2fa_operations_total.labels(
            operation="verify_login", status="user_error"
        ).inc()
        raise HTTPException(status_code=401, detail="Invalid authentication state")

    if not verify_totp(user.totp_secret, code):
        logger.warning(
            "2fa_login_verification_failed",
            username=user.username,
            user_id=user.id,
        )
        auth_2fa_operations_total.labels(
            operation="verify_login", status="invalid_code"
        ).inc()
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    # 2FA verified — issue the real JWT
    token = create_access_token({"sub": str(user.id), "username": user.username})
    logger.info("user_logged_in_2fa", username=user.username, user_id=user.id)
    auth_logins_total.labels(status="success").inc()
    auth_2fa_operations_total.labels(
        operation="verify_login", status="success"
    ).inc()

    # Fire-and-forget Kafka event
    await produce_event(
        "user_logged_in", {"user_id": user.id, "username": user.username}
    )

    return TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )


def get_2fa_status(db: Session, user_info: dict) -> dict:
    """Return the current 2FA status for the authenticated user."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"is_2fa_enabled": user.is_2fa_enabled}
