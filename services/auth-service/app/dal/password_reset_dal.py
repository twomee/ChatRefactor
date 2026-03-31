# app/dal/password_reset_dal.py — Data Access Layer for PasswordResetToken model
"""
Pure database operations for password-reset tokens.
No business logic, no HTTP concerns.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import PasswordResetToken


def create_token(
    db: Session, user_id: int, token: str, expires_at: datetime
) -> PasswordResetToken:
    """Persist a new password-reset token and return it."""
    reset_token = PasswordResetToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()
    db.refresh(reset_token)
    return reset_token


def get_valid_token(db: Session, token: str) -> PasswordResetToken | None:
    """Return the token if it exists, is not expired, and has not been used."""
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == token,
            PasswordResetToken.used == False,  # noqa: E712  — SQLAlchemy requires == for filter
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )


def mark_token_used(db: Session, token: str) -> None:
    """Mark a password-reset token as used so it cannot be reused."""
    row = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if row:
        row.used = True
        db.commit()


def cleanup_expired(db: Session) -> int:
    """Delete expired or used tokens. Returns the number of rows removed."""
    count = (
        db.query(PasswordResetToken)
        .filter(
            (PasswordResetToken.expires_at <= datetime.now(timezone.utc))
            | (PasswordResetToken.used == True)  # noqa: E712
        )
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return count
