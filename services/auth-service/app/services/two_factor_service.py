# app/services/two_factor_service.py — 2FA business logic (setup, verify, disable, login)
"""
Extracted from auth_service.py for Single Responsibility.
Handles all two-factor authentication flows:
- Temp token management (store, peek, consume) via Redis
- 2FA setup and verification
- 2FA disable
- 2FA-protected login completion
- 2FA status queries
"""

import base64
import io
import json
import secrets

import qrcode
from sqlalchemy.orm import Session

from app.services.exceptions import (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    ServerError,
)

from app.core.logging import get_logger
from app.core.security import create_access_token
from app.dal import user_dal
from app.infrastructure.kafka_producer import produce_event
from app.infrastructure.metrics import auth_2fa_operations_total, auth_logins_total
from app.infrastructure.redis import get_redis
from app.schemas.auth import TokenResponse
from app.utils.encryption import decrypt_totp_secret, encrypt_totp_secret
from app.utils.totp import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)

logger = get_logger("services.two_factor")

# Module-level constants
_2FA_TEMP_TOKEN_TTL = 300  # 5 minutes
_2FA_TEMP_TOKEN_PREFIX = "2fa_temp:"
_INVALID_TOTP = "Invalid TOTP code"
_USER_NOT_FOUND = "User not found"


def check_and_mark_totp_replay(user_id: int, code: str) -> bool:
    """Check for TOTP replay attack and mark the code as used.

    Returns True if the code was already used (replay detected), False otherwise.
    """
    r = get_redis()
    replay_key = f"totp_used:{user_id}:{code}"
    already_used = r.get(replay_key)
    if already_used:
        return True
    r.setex(replay_key, 90, "1")
    return False


# ── Temp token helpers ──────────────────────────────────────────────────


def store_2fa_temp_token(user_id: int, username: str) -> str:
    """Generate a cryptographic temp token and store it in Redis with a 5-min TTL.

    The token maps to the user_id + username so we can issue a real JWT after
    the TOTP code is verified without re-authenticating the password.
    """
    token = secrets.token_urlsafe(48)
    payload = json.dumps({"user_id": user_id, "username": username})
    get_redis().setex(f"{_2FA_TEMP_TOKEN_PREFIX}{token}", _2FA_TEMP_TOKEN_TTL, payload)
    return token


def peek_2fa_temp_token(temp_token: str) -> dict | None:
    """Read temp token data without consuming it.

    Used to validate the token before TOTP verification so that a wrong TOTP
    code does not force the user to restart the entire login flow.
    """
    raw = get_redis().get(f"{_2FA_TEMP_TOKEN_PREFIX}{temp_token}")
    if raw is None:
        return None
    return json.loads(raw)


def consume_2fa_temp_token(temp_token: str) -> dict | None:
    """Read and delete a 2FA temp token from Redis (single-use).

    Returns the stored user info dict or None if the token is expired/invalid.
    Call this ONLY after TOTP verification succeeds to ensure users can retry
    a failed code without restarting the login flow.
    """
    r = get_redis()
    key = f"{_2FA_TEMP_TOKEN_PREFIX}{temp_token}"
    raw = r.get(key)
    if raw is None:
        return None
    r.delete(key)  # single-use: consume only on success
    return json.loads(raw)


# ── QR code generation ──────────────────────────────────────────────────


def generate_qr_code_data_uri(otpauth_uri: str) -> str:
    """Generate a QR code PNG as a base64 data URI."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


# ── 2FA service functions ───────────────────────────────────────────────


def setup_2fa(db: Session, user_info: dict) -> dict:
    """Generate a TOTP secret, encrypt it, and store it (not yet enabled).

    Returns a server-generated QR code image (base64 PNG) and the manual entry
    key. The raw otpauth URI is NOT returned to avoid leaking it in the DOM.
    The user must call verify-setup with a valid code to actually enable 2FA.
    """
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise NotFoundError(_USER_NOT_FOUND)
    if user.is_2fa_enabled:
        raise BadRequestError("2FA is already enabled")

    secret = generate_totp_secret()
    # Encrypt before storing — plaintext secret never hits the database
    user_dal.update_2fa_secret(db, user.id, encrypt_totp_secret(secret))

    uri = get_totp_uri(secret, user.username)
    logger.info("2fa_setup_initiated", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(operation="setup", status="initiated").inc()

    return {
        "qr_code": generate_qr_code_data_uri(uri),
        "manual_entry_key": secret,  # Required for manual authenticator entry
        # NOTE: otpauth_uri intentionally omitted — QR code is served server-side
    }


def verify_2fa_setup(db: Session, user_info: dict, code: str) -> dict:
    """Confirm 2FA setup by verifying a TOTP code, then enable 2FA on the account."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise NotFoundError(_USER_NOT_FOUND)
    if user.is_2fa_enabled:
        raise BadRequestError("2FA is already enabled")
    if not user.totp_secret:
        raise BadRequestError("Call /auth/2fa/setup first")

    plaintext_secret = decrypt_totp_secret(user.totp_secret)

    if not verify_totp(plaintext_secret, code):
        logger.warning(
            "2fa_setup_verification_failed",
            username=user.username,
            user_id=user.id,
        )
        auth_2fa_operations_total.labels(
            operation="verify_setup", status="invalid_code"
        ).inc()
        raise BadRequestError(_INVALID_TOTP)

    user_dal.enable_2fa(db, user.id)
    logger.info("2fa_enabled", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(operation="verify_setup", status="success").inc()

    return {"message": "2FA enabled successfully"}


def disable_2fa(db: Session, user_info: dict, code: str) -> dict:
    """Disable 2FA after verifying a TOTP code (proof that the user owns the secret)."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise NotFoundError(_USER_NOT_FOUND)
    if not user.is_2fa_enabled:
        raise BadRequestError("2FA is not enabled")

    # Null check: totp_secret must be present if 2FA is flagged as enabled
    if not user.totp_secret:
        raise ServerError(
            "Authentication state corrupted: 2FA enabled but no secret configured"
        )

    plaintext_secret = decrypt_totp_secret(user.totp_secret)

    if not verify_totp(plaintext_secret, code):
        logger.warning("2fa_disable_failed", username=user.username, user_id=user.id)
        auth_2fa_operations_total.labels(
            operation="disable", status="invalid_code"
        ).inc()
        raise BadRequestError(_INVALID_TOTP)

    # Replay attack protection for disable flow
    if check_and_mark_totp_replay(user.id, code):
        logger.warning(
            "2fa_disable_replay_detected", username=user.username, user_id=user.id
        )
        auth_2fa_operations_total.labels(
            operation="disable", status="replay_detected"
        ).inc()
        raise BadRequestError(_INVALID_TOTP)

    user_dal.disable_2fa(db, user.id)
    logger.info("2fa_disabled", username=user.username, user_id=user.id)
    auth_2fa_operations_total.labels(operation="disable", status="success").inc()

    return {"message": "2FA disabled successfully"}


async def verify_login_2fa(db: Session, temp_token: str, code: str) -> TokenResponse:
    """Complete a 2FA-protected login by verifying the temp_token + TOTP code.

    Peeks at (but does not consume) the single-use temp_token first, so that
    a wrong TOTP code does not force the user to restart the entire login flow.
    Only consumes (deletes) the token after successful TOTP verification.
    """
    # Peek first — do not consume the token before TOTP is verified.
    # This ensures a wrong code lets the user retry without re-entering credentials.
    user_data = peek_2fa_temp_token(temp_token)
    if user_data is None:
        auth_2fa_operations_total.labels(
            operation="verify_login", status="expired_token"
        ).inc()
        raise AuthenticationError("Temp token expired or invalid — please log in again")

    user = user_dal.get_by_id(db, user_data["user_id"])
    if not user or not user.is_2fa_enabled or not user.totp_secret:
        auth_2fa_operations_total.labels(
            operation="verify_login", status="user_error"
        ).inc()
        raise AuthenticationError("Invalid authentication state")

    plaintext_secret = decrypt_totp_secret(user.totp_secret)

    if not verify_totp(plaintext_secret, code):
        logger.warning(
            "2fa_login_verification_failed",
            username=user.username,
            user_id=user.id,
        )
        auth_2fa_operations_total.labels(
            operation="verify_login", status="invalid_code"
        ).inc()
        # Token is NOT consumed — user can retry with a new code
        raise AuthenticationError(_INVALID_TOTP)

    # Replay attack protection: reject a code that was already used
    if check_and_mark_totp_replay(user.id, code):
        logger.warning(
            "2fa_login_replay_detected", username=user.username, user_id=user.id
        )
        auth_2fa_operations_total.labels(
            operation="verify_login", status="replay_detected"
        ).inc()
        raise AuthenticationError(_INVALID_TOTP)

    # TOTP verified and not a replay — now consume the temp token (single-use)
    consume_2fa_temp_token(temp_token)

    # 2FA verified — issue the real JWT
    token = create_access_token({"sub": str(user.id), "username": user.username})
    logger.info("user_logged_in_2fa", username=user.username, user_id=user.id)
    auth_logins_total.labels(status="success").inc()
    auth_2fa_operations_total.labels(operation="verify_login", status="success").inc()

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


def get_2fa_status(db: Session, user_info: dict) -> dict:
    """Return the current 2FA status for the authenticated user."""
    user = user_dal.get_by_id(db, user_info["user_id"])
    if not user:
        raise NotFoundError(_USER_NOT_FOUND)
    return {"is_2fa_enabled": user.is_2fa_enabled}
