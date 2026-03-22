# app/dal/user_dal.py — Data Access Layer for User model
"""
Pure database operations — no business logic, no HTTP concerns.
Each function takes a SQLAlchemy Session and returns model instances or None.
"""
from sqlalchemy.orm import Session

from app.models import User


def get_by_id(db: Session, user_id: int) -> User | None:
    """Look up a user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


def get_by_username(db: Session, username: str) -> User | None:
    """Look up a user by username (case-sensitive)."""
    return db.query(User).filter(User.username == username).first()


def create(db: Session, username: str, password_hash: str, is_global_admin: bool = False) -> User:
    """Create a new user and return the committed instance."""
    user = User(username=username, password_hash=password_hash, is_global_admin=is_global_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_all(db: Session):
    """Delete all users. Used only in tests."""
    db.query(User).delete()
    db.commit()
