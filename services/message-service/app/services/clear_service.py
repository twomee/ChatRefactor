# app/services/clear_service.py — Business logic for clear history and PM deletion
#
# Extracts clear/deletion logic from routers/messages.py so the router
# remains a thin HTTP adapter.
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dal import clear_dal, pm_deletion_dal
from app.schemas.message import MessageResponse

logger = get_logger("services.clear")


def clear_history(
    db: Session,
    user_id: int,
    context_type: str,
    context_id: int,
) -> None:
    """Clear a user's view of a conversation (room or PM)."""
    clear_dal.upsert_clear(db, user_id, context_type, context_id)


def delete_pm_conversation(
    db: Session,
    user_id: int,
    other_user_id: int,
) -> None:
    """Delete a PM conversation from the current user's view."""
    pm_deletion_dal.delete_conversation(db, user_id, other_user_id)


def get_deleted_conversations(db: Session, user_id: int) -> list[dict]:
    """Return all deleted PM conversations for a user."""
    return pm_deletion_dal.get_deleted_conversations(db, user_id)


def apply_clear_filter(
    db: Session,
    user_id: int,
    context_type: str,
    context_id: int,
    messages: list[MessageResponse],
) -> list[MessageResponse]:
    """Filter out messages that were sent before the user's clear timestamp.

    If the user has not cleared this context, returns all messages unchanged.
    """
    cleared_at: datetime | None = clear_dal.get_clear(
        db, user_id, context_type, context_id
    )
    if cleared_at is None:
        return messages

    return [m for m in messages if m.sent_at > cleared_at]


def apply_pm_deletion_filter(
    db: Session,
    user_id: int,
    other_user_id: int,
    messages: list[MessageResponse],
) -> list[MessageResponse]:
    """Filter out PM messages sent before the user deleted the conversation."""
    deleted_at: datetime | None = pm_deletion_dal.get_pm_deletion_timestamp(
        db, user_id, other_user_id
    )
    if deleted_at is None:
        return messages

    return [m for m in messages if m.sent_at > deleted_at]
