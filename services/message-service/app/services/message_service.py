# app/services/message_service.py — Business logic for message REST endpoints
#
# Service layer between routers and DAL. Handles orchestration logic such as
# auth-service calls, clear/deletion filtering, and reaction enrichment.
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dal import message_dal, reaction_dal
from app.infrastructure.auth_client import get_user_by_username
from app.schemas.message import MessageResponse
from app.services.clear_service import apply_clear_filter, apply_pm_deletion_filter

logger = get_logger("services.message")


def get_replay_messages(
    db: Session, room_id: int, since: datetime, limit: int = 100
) -> list[MessageResponse]:
    """Fetch messages in a room since a given timestamp (for replay after reconnect)."""
    messages = message_dal.get_by_room_since(db, room_id, since, limit)
    return [MessageResponse.model_validate(m) for m in messages]


def get_room_history(
    db: Session, room_id: int, limit: int = 50
) -> list[MessageResponse]:
    """Fetch recent room history (for initial room join)."""
    messages = message_dal.get_room_history(db, room_id, limit)
    return [MessageResponse.model_validate(m) for m in messages]


async def get_pm_history(
    db: Session,
    user_id: int,
    username: str,
    limit: int = 50,
    before: str | None = None,
) -> list[dict]:
    """Fetch PM history between the current user and another user.

    Resolves the other user via auth service, applies clear and deletion
    filters, and enriches with reactions.

    Raises:
        HTTPException: 404 if user not found, 422 if ``before`` is invalid.
    """
    from fastapi import HTTPException

    other = await get_user_by_username(username)
    if not other:
        raise HTTPException(status_code=404, detail="User not found")

    other_id: int = other["id"]

    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Invalid 'before' timestamp format"
            )

    messages = message_dal.get_pm_history(
        db, me_id=user_id, other_id=other_id, limit=limit, before=before_dt
    )
    validated = [MessageResponse.model_validate(m) for m in messages]

    # Apply UserMessageClear filter
    validated = apply_clear_filter(db, user_id, "pm", other_id, validated)

    # Apply DeletedPMConversation filter
    validated = apply_pm_deletion_filter(db, user_id, other_id, validated)

    return enrich_with_reactions(db, validated)


def get_message_context(
    db: Session,
    room_id: int,
    message_id: str,
    before: int = 25,
    after: int = 25,
) -> list[dict]:
    """Get messages around a target message in a room (for scroll-to-message).

    Returns up to ``before`` messages before and ``after`` messages after the
    target message, sorted chronologically.

    Raises:
        HTTPException: 404 if message not found in this room.
    """
    from fastapi import HTTPException

    messages = message_dal.get_messages_around(db, room_id, message_id, before, after)
    if not messages:
        raise HTTPException(status_code=404, detail="Message not found in this room")

    return [
        {
            "message_id": m.message_id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "room_id": m.room_id,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "is_deleted": m.is_deleted,
        }
        for m in messages
    ]


def get_pm_context(
    db: Session,
    user_id: int,
    message_id: str,
    before: int = 25,
    after: int = 25,
) -> list[dict]:
    """Get messages around a target PM message (for scroll-to-message).

    Returns up to ``before`` messages before and ``after`` messages after the
    target PM message in the same conversation, sorted chronologically.

    Raises:
        HTTPException: 404 if PM message not found.
    """
    from fastapi import HTTPException

    messages = message_dal.get_pm_messages_around(
        db, user_id, message_id, before, after
    )
    if not messages:
        raise HTTPException(status_code=404, detail="PM message not found")

    return [
        {
            "message_id": m.message_id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "recipient_id": m.recipient_id,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            "is_deleted": m.is_deleted,
        }
        for m in messages
    ]


def enrich_with_reactions(db: Session, messages: list[MessageResponse]) -> list[dict]:
    """Attach reactions to each message response.

    Fetches reactions in a single batch query for all message_ids, then
    merges them into the response dicts.
    """
    msg_ids = [m.message_id for m in messages if m.message_id]
    reactions_map = reaction_dal.get_reactions_for_messages(db, msg_ids)

    enriched = []
    for m in messages:
        d = m.model_dump()
        d["reactions"] = reactions_map.get(m.message_id, [])
        enriched.append(d)
    return enriched
