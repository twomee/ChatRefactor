# app/dal/user_dal.py — Data Access Layer for User model
"""
Pure database operations — no business logic, no HTTP concerns.
Each function takes a SQLAlchemy Session and returns model instances or None.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User


def get_by_id(db: Session, user_id: int) -> User | None:
    """Look up a user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


def get_by_username(db: Session, username: str) -> User | None:
    """Look up a user by username (case-insensitive)."""
    return db.query(User).filter(func.lower(User.username) == username.lower()).first()


def get_by_email(db: Session, email: str) -> User | None:
    """Look up a user by email address (case-insensitive)."""
    return db.query(User).filter(func.lower(User.email) == email.lower()).first()


def create(
    db: Session,
    username: str,
    password_hash: str,
    is_global_admin: bool = False,
    email: str | None = None,
) -> User:
    """Create a new user and return the committed instance."""
    user = User(
        username=username,
        password_hash=password_hash,
        is_global_admin=is_global_admin,
        email=email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_2fa_secret(db: Session, user_id: int, totp_secret: str | None) -> None:
    """Set or clear the TOTP secret for a user (setup phase, not yet enabled)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.totp_secret = totp_secret
        db.commit()


def enable_2fa(db: Session, user_id: int) -> None:
    """Mark 2FA as enabled after the user has verified their TOTP setup."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_2fa_enabled = True
        db.commit()


def disable_2fa(db: Session, user_id: int) -> None:
    """Disable 2FA and clear the TOTP secret and backup codes."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_2fa_enabled = False
        user.totp_secret = None
        user.backup_codes = None
        db.commit()


def update_email(db: Session, user_id: int, email: str) -> None:
    """Update a user's email address."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.email = email
        db.commit()


def update_password(db: Session, user_id: int, password_hash: str) -> None:
    """Update a user's password hash."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.password_hash = password_hash
        db.commit()


def delete_all(db: Session):
    """Delete all users. Used only in tests."""
    db.query(User).delete()
    db.commit()
