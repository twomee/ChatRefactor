# app/services/password_reset_service.py — Business logic for forgot/reset password
"""
Two-step flow:
1. request_reset(email) — looks up user, generates token, sends email.
   Always returns success (no email enumeration).
2. reset_password(token, new_password) — validates token, updates password,
   marks token as used.
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import hash_password
from app.dal import password_reset_dal, user_dal
from app.services.email_service import EmailSender, create_email_sender
from app.services.exceptions import BadRequestError

logger = get_logger("services.password_reset")

_TOKEN_EXPIRY_HOURS = 1


def request_reset(
    db: Session, email: str, email_sender: EmailSender | None = None
) -> dict:
    """Initiate a password-reset flow.

    Looks up the user by email, generates a secure token, stores it with
    a 1-hour expiry, and sends a reset email. If the email does not match
    any user, the function still returns success to prevent email enumeration.
    """
    if email_sender is None:
        email_sender = create_email_sender()

    user = user_dal.get_by_email(db, email)
    if user:
        token = secrets.token_hex(32)  # 32 bytes = 64 hex chars
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRY_HOURS)
        password_reset_dal.create_token(db, user.id, token, expires_at)

        # Build and send the reset email
        reset_link = f"https://chatbox.local/reset-password?token={token}"
        body = (
            f"<p>Hello {user.username},</p>"
            f"<p>Click the link below to reset your password:</p>"
            f'<p><a href="{reset_link}">{reset_link}</a></p>'
            f"<p>This link expires in {_TOKEN_EXPIRY_HOURS} hour(s).</p>"
            f"<p>If you did not request this, ignore this email.</p>"
        )
        try:
            email_sender.send(email, "cHATBOX — Password Reset", body)
        except Exception:
            logger.error("password_reset_email_failed", email=email)
            # Don't fail the request — the token is still valid

        logger.info("password_reset_requested", user_id=user.id)
    else:
        # Log for auditing but do not reveal whether the email exists
        logger.info("password_reset_requested_unknown_email", email=email)

    return {"message": "If that email is registered, a reset link has been sent."}


def reset_password(db: Session, token: str, new_password: str) -> dict:
    """Complete the password-reset flow.

    Validates the token, hashes the new password, updates the user's
    password, and marks the token as used. Returns 400 if the token is
    invalid, expired, or already used.
    """
    reset_token = password_reset_dal.get_valid_token(db, token)
    if not reset_token:
        raise BadRequestError("Invalid or expired reset token")

    user = user_dal.get_by_id(db, reset_token.user_id)
    if not user:
        raise BadRequestError("Invalid or expired reset token")

    user_dal.update_password(db, user.id, hash_password(new_password))
    password_reset_dal.mark_token_used(db, token)
    logger.info("password_reset_completed", user_id=user.id)

    return {"message": "Password has been reset successfully"}
