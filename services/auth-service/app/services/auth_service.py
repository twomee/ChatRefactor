# app/services/auth_service.py — Business logic for registration, login, logout, ping
"""
Key differences from monolith:
1. NO ConnectionManager dependency — auth service doesn't manage WebSocket presence.
   Presence is handled by the Chat Service, which consumes auth.events from Kafka.
2. Produces Kafka events (fire-and-forget) for user_registered, user_logged_in, user_logged_out.
3. ping simply returns ok — no presence management needed.
4. 2FA (TOTP) support has been extracted to two_factor_service.py and utils/totp.py.
"""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ACCESS_TOKEN_EXPIRE_HOURS, APP_ENV
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.dal import user_dal
from app.infrastructure.kafka_producer import produce_event
from app.infrastructure.metrics import (
    auth_logins_total,
    auth_logouts_total,
    auth_registrations_total,
)
from app.schemas.auth import TokenResponse, UserLogin, UserRegister
from app.services.two_factor_service import store_2fa_temp_token

logger = get_logger("services.auth")

# Module-level string constants to avoid S1192 duplication warnings
_USER_NOT_FOUND = "User not found"


async def register(db: Session, body: UserRegister) -> dict:
    """Register a new user.

    Flow: check duplicate username -> check duplicate email -> hash password -> persist -> produce event.
    Input validation (username format, password length, email format) is handled by the
    Pydantic schema (UserRegister) before this function is called.
    The Kafka event is fire-and-forget: registration succeeds even if Kafka is down.
    """
    if user_dal.get_by_username(db, body.username):
        auth_registrations_total.labels(status="duplicate").inc()
        raise HTTPException(status_code=409, detail="Username already taken")

    if user_dal.get_by_email(db, body.email):
        auth_registrations_total.labels(status="duplicate").inc()
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        user = user_dal.create(
            db,
            username=body.username,
            password_hash=hash_password(body.password),
            email=body.email,
        )
    except IntegrityError:
        db.rollback()
        auth_registrations_total.labels(status="duplicate").inc()
        raise HTTPException(status_code=409, detail="Username or email already taken")

    logger.info("user_registered", username=user.username, user_id=user.id)
    auth_registrations_total.labels(status="success").inc()

    # Fire-and-forget Kafka event — don't fail registration if Kafka is down
    await produce_event(
        "user_registered", {"user_id": user.id, "username": user.username}
    )

    return {"message": "Registered successfully"}


# ═══════════════════════════════════════════════════════════════════════════
#  Profile / Settings
# ═══════════════════════════════════════════════════════════════════════════


def get_profile(db: Session, user_id: int) -> dict:
    """Return the authenticated user's profile (username + email)."""
    user = user_dal.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    return {"username": user.username, "email": user.email}


def update_email(
    db: Session, user_id: int, new_email: str, current_password: str
) -> dict:
    """Change the user's email after verifying their current password.

    Checks: password correct, new email not already taken, then updates.
    """
    user = user_dal.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    existing = user_dal.get_by_email(db, new_email)
    if existing and existing.id != user_id:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_dal.update_email(db, user_id, new_email)
    logger.info("email_updated", user_id=user_id)
    return {"message": "Email updated successfully"}


def update_password(
    db: Session, user_id: int, current_password: str, new_password: str
) -> dict:
    """Change the user's password after verifying their current password."""
    user = user_dal.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user_dal.update_password(db, user_id, hash_password(new_password))
    logger.info("password_updated", user_id=user_id)
    return {"message": "Password updated successfully"}


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
        temp_token = store_2fa_temp_token(user.id, user.username)
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
        user_id=user.id,
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
