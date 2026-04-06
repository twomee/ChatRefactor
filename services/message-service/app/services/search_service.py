# app/services/search_service.py — Business logic for message search
#
# Extracts search + clear-filter logic from routers/messages.py so the
# router remains a thin HTTP adapter.
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dal import clear_dal, message_dal

logger = get_logger("services.search")


def search_messages(
    db: Session,
    user_id: int,
    query: str,
    room_id: int | None,
    limit: int,
) -> list[dict]:
    """Search messages and apply per-user clear filters.

    When ``room_id`` is provided, applies a single-room clear filter.
    When ``room_id`` is None (cross-room search), fetches all of the user's
    room clear records in one query to avoid N+1.

    Returns a list of dicts ready for the API response.
    """
    results = message_dal.search_messages(db, query=query, room_id=room_id, limit=limit)

    if room_id is not None:
        # Scoped to a single room -- use the single-room clear helper.
        cleared_at = clear_dal.get_clear(db, user_id, "room", room_id)
        if cleared_at is not None:
            results = [m for m in results if m.sent_at > cleared_at]
    else:
        # Cross-room search -- fetch ALL of the user's room clear records in one
        # query and apply them per-room without N+1 queries.
        clears = clear_dal.get_all_clears_for_user(db, user_id, "room")
        if clears:
            results = [
                m
                for m in results
                if m.room_id is None
                or m.room_id not in clears
                or m.sent_at > clears[m.room_id]
            ]

    return [
        {
            "message_id": m.message_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "room_id": m.room_id,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        }
        for m in results
    ]
