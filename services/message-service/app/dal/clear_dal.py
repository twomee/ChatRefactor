# app/dal/clear_dal.py — Data Access Layer for UserMessageClear model
#
# Provides upsert and lookup operations for per-user conversation clear
# timestamps. Uses SQLAlchemy ORM (not raw SQL) for SQLite test compatibility.
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import UserMessageClear


def upsert_clear(
    db: Session,
    user_id: int,
    context_type: str,
    context_id: int,
) -> UserMessageClear:
    """Insert or update a clear marker for a user's conversation context.

    If a clear record already exists for this (user_id, context_type, context_id),
    updates cleared_at to the current time. Otherwise creates a new record.
    This is SQLite-compatible (no ON CONFLICT ... DO UPDATE).
    """
    existing = (
        db.query(UserMessageClear)
        .filter(
            UserMessageClear.user_id == user_id,
            UserMessageClear.context_type == context_type,
            UserMessageClear.context_id == context_id,
        )
        .first()
    )

    if existing:
        existing.cleared_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    record = UserMessageClear(
        user_id=user_id,
        context_type=context_type,
        context_id=context_id,
        cleared_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_clear(
    db: Session,
    user_id: int,
    context_type: str,
    context_id: int,
) -> datetime | None:
    """Return the cleared_at timestamp for a user's context, or None if not cleared."""
    record = (
        db.query(UserMessageClear)
        .filter(
            UserMessageClear.user_id == user_id,
            UserMessageClear.context_type == context_type,
            UserMessageClear.context_id == context_id,
        )
        .first()
    )
    return record.cleared_at if record else None


def get_all_clears_for_user(
    db: Session,
    user_id: int,
    context_type: str,
) -> dict[int, datetime]:
    """Return all cleared_at timestamps for a user's contexts of a given type.

    Returns a mapping of ``{context_id: cleared_at}`` so callers can apply
    per-room (or per-PM) clear filters without N+1 queries.
    """
    records = (
        db.query(UserMessageClear)
        .filter(
            UserMessageClear.user_id == user_id,
            UserMessageClear.context_type == context_type,
        )
        .all()
    )
    return {r.context_id: r.cleared_at for r in records}
