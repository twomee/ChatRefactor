# app/dal/pm_deletion_dal.py — Data Access Layer for DeletedPMConversation model
#
# Provides upsert, list, and remove operations for per-user PM conversation
# deletions. Uses SQLAlchemy ORM (not raw SQL) for SQLite test compatibility.
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import DeletedPMConversation


def delete_conversation(
    db: Session,
    user_id: int,
    other_user_id: int,
) -> DeletedPMConversation:
    """Mark a PM conversation as deleted for a user (upsert).

    If a deletion record already exists, updates deleted_at to the current time.
    Otherwise creates a new record. Does NOT delete any messages from the database.
    """
    existing = (
        db.query(DeletedPMConversation)
        .filter(
            DeletedPMConversation.user_id == user_id,
            DeletedPMConversation.other_user_id == other_user_id,
        )
        .first()
    )

    if existing:
        existing.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    record = DeletedPMConversation(
        user_id=user_id,
        other_user_id=other_user_id,
        deleted_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_deleted_conversations(
    db: Session,
    user_id: int,
) -> list[dict]:
    """Return all deleted PM conversations for a user.

    Returns a list of dicts with other_user_id and deleted_at.
    """
    records = (
        db.query(DeletedPMConversation)
        .filter(DeletedPMConversation.user_id == user_id)
        .order_by(DeletedPMConversation.deleted_at.desc())
        .all()
    )
    return [
        {
            "other_user_id": r.other_user_id,
            "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
        }
        for r in records
    ]


def remove_deletion(
    db: Session,
    user_id: int,
    other_user_id: int,
) -> bool:
    """Remove a deletion record (restore the conversation). Returns True if removed."""
    count = (
        db.query(DeletedPMConversation)
        .filter(
            DeletedPMConversation.user_id == user_id,
            DeletedPMConversation.other_user_id == other_user_id,
        )
        .delete()
    )
    db.commit()
    return count > 0


def get_pm_deletion_timestamp(
    db: Session,
    user_id: int,
    other_user_id: int,
) -> datetime | None:
    """Return the deleted_at timestamp for a specific PM conversation, or None.

    Mirrors clear_dal.get_clear — used by the PM history endpoint to filter
    messages sent before the user deleted this conversation.
    """
    record = (
        db.query(DeletedPMConversation)
        .filter(
            DeletedPMConversation.user_id == user_id,
            DeletedPMConversation.other_user_id == other_user_id,
        )
        .first()
    )
    return record.deleted_at if record else None
