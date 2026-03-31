# app/routers/messages.py — Message replay, history, edit, delete, reaction,
#                          clear, context, and PM deletion API
#
# CQRS READ side: these endpoints read from the messages database that is populated
# by the Kafka consumer (WRITE side). All endpoints require JWT authentication.
#
# Key difference from monolith:
# - No room existence check (rooms live in a different service/database)
# - get_current_user returns a dict, not a User ORM object
# - Sender names are NOT resolved here (would require auth service call per message)
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.dal import message_dal
from app.dal import reaction_dal
from app.dal import clear_dal
from app.dal import pm_deletion_dal
from app.infrastructure.auth_client import get_user_by_username
from app.infrastructure.redis_client import get_redis
from app.schemas.message import (
    ClearHistoryRequest,
    DeletePMConversationRequest,
    MessageResponse,
    MessageWithReactionsResponse,
)
from app.services import message_service
from app.services.url_preview_service import (
    cache_preview,
    fetch_preview,
    get_cached_preview,
)

router = APIRouter(prefix="/messages", tags=["messages"])


class EditMessageBody(BaseModel):
    """Request body for editing a message."""

    content: str


# ── Search endpoint (defined BEFORE /{message_id}/* routes to avoid
#    FastAPI matching "search" as a path parameter) ──────────────────


@router.get("/search", responses={400: {"description": "Query cannot be empty"}})
def search_messages_endpoint(
    q: Annotated[
        str,
        Query(
            ...,
            min_length=2,
            max_length=200,
            description="Search query (minimum 2 characters)",
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    room_id: Annotated[
        int | None,
        Query(
            description="Room ID to search within (optional — omit to search all rooms)",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Search messages by text content within a specific room.

    Uses PostgreSQL full-text search (tsvector + GIN index) for relevance-ranked
    results. Only public, non-deleted messages are searched.

    `room_id` is required: callers must specify which room to search. This prevents
    authenticated users from enumerating messages in rooms they have not joined —
    the chat-service's WebSocket join authorization is the membership enforcement
    point, and requiring room_id here keeps the search scoped to a single room.

    Query params:
      - q: search terms (2-200 chars); min of 2 chars avoids full GIN index scans
      - room_id: room to search (required)
      - limit: max results (1-100, default 20)
    """
    stripped = q.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = message_dal.search_messages(
        db, query=stripped, room_id=room_id, limit=limit
    )
    # Apply per-user clear filter so cleared messages don't appear in search results.
    user_id = current_user["user_id"]
    if room_id is not None:
        # Scoped to a single room — use the single-room helper.
        results = _apply_clear_filter(db, user_id, "room", room_id, results)
    else:
        # Cross-room search — fetch ALL of the user's room clear records in one
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


# ── Clear history endpoint ──────────────────────────────────────────


@router.post("/clear", status_code=200)
def clear_history(
    body: ClearHistoryRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Clear a user's view of a conversation (room or PM).

    Records a timestamp — messages sent before this time are hidden from
    the requesting user only. Other participants are unaffected.
    Idempotent: re-clearing updates the timestamp.
    """
    clear_dal.upsert_clear(
        db, current_user["user_id"], body.context_type, body.context_id
    )
    return {"detail": "History cleared"}


# ── PM deletion endpoints ──────────────────────────────────────────


@router.post("/pm/delete-conversation", status_code=200)
def delete_pm_conversation(
    body: DeletePMConversationRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Delete a PM conversation from the current user's view.

    Records a deletion marker — PM messages with this user before the
    deletion timestamp are hidden. The other user's view is unaffected.
    Idempotent: re-deleting updates the timestamp.
    """
    pm_deletion_dal.delete_conversation(db, current_user["user_id"], body.other_user_id)
    return {"detail": "Conversation deleted"}


@router.get("/pm/deleted-conversations")
def get_deleted_pm_conversations(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return all deleted PM conversations for the current user."""
    return pm_deletion_dal.get_deleted_conversations(db, current_user["user_id"])


@router.get(
    "/pm/history/{username}",
    response_model=list[MessageWithReactionsResponse],
    responses={
        404: {"description": "User not found"},
        422: {"description": "Invalid 'before' timestamp format"},
    },
)
async def get_pm_history_endpoint(
    username: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[
        str | None,
        Query(description="ISO timestamp — return messages before this time"),
    ] = None,
):
    """Fetch PM history between the current user and another user.

    Applies UserMessageClear and DeletedPMConversation filters so cleared/
    deleted history is never returned. Supports backward pagination via
    the `before` query parameter (ISO 8601 timestamp).
    """
    other = await get_user_by_username(username)
    if not other:
        raise HTTPException(status_code=404, detail="User not found")

    me_id: int = current_user["user_id"]
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
        db, me_id=me_id, other_id=other_id, limit=limit, before=before_dt
    )
    validated = [MessageResponse.model_validate(m) for m in messages]

    # Apply UserMessageClear filter
    validated = _apply_clear_filter(db, me_id, "pm", other_id, validated)

    # Apply DeletedPMConversation filter
    deleted_at = pm_deletion_dal.get_pm_deletion_timestamp(db, me_id, other_id)
    if deleted_at is not None:
        validated = [m for m in validated if m.sent_at > deleted_at]

    return _enrich_with_reactions(db, validated)


# ── Context endpoints (scroll-to-message for search results) ───────


@router.get(
    "/rooms/{room_id}/context",
    responses={404: {"description": "Message not found in this room"}},
)
def get_message_context(
    room_id: int,
    message_id: Annotated[str, Query(..., description="Target message UUID")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    before: Annotated[int, Query(ge=0, le=100)] = 25,
    after: Annotated[int, Query(ge=0, le=100)] = 25,
):
    """Get messages around a target message in a room (for scroll-to-message).

    Returns up to `before` messages before and `after` messages after the
    target message, sorted chronologically. Used when a user clicks a search
    result to see the surrounding conversation context.
    """
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


@router.get(
    "/pm/context",
    responses={404: {"description": "PM message not found"}},
)
def get_pm_context(
    message_id: Annotated[str, Query(..., description="Target PM message UUID")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    before: Annotated[int, Query(ge=0, le=100)] = 25,
    after: Annotated[int, Query(ge=0, le=100)] = 25,
):
    """Get messages around a target PM message (for scroll-to-message).

    Returns up to `before` messages before and `after` messages after the
    target PM message in the same conversation, sorted chronologically.
    """
    messages = message_dal.get_pm_messages_around(
        db, current_user["user_id"], message_id, before, after
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


# ── Room replay & history endpoints ────────────────────────────────


@router.get("/rooms/{room_id}", response_model=list[MessageWithReactionsResponse])
def get_room_messages(
    room_id: int,
    since: Annotated[
        datetime,
        Query(..., description="ISO 8601 timestamp — return messages after this time"),
    ],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """
    Replay endpoint: fetch messages in a room since a given timestamp.

    Use case: client reconnects after a disconnect, provides the timestamp of the
    last message it received, and gets everything it missed.

    Respects per-user clear markers: if the user has cleared this room,
    only messages after cleared_at are returned.
    """
    messages = message_service.get_replay_messages(db, room_id, since, limit)
    messages = _apply_clear_filter(
        db, current_user["user_id"], "room", room_id, messages
    )
    return _enrich_with_reactions(db, messages)


@router.get(
    "/rooms/{room_id}/history", response_model=list[MessageWithReactionsResponse]
)
def get_room_history(
    room_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    History endpoint: fetch the most recent messages in a room.

    Use case: user joins a room and wants to see what was recently discussed.
    Returns messages in chronological order (oldest first).

    Respects per-user clear markers: if the user has cleared this room,
    only messages after cleared_at are returned.
    """
    messages = message_service.get_room_history(db, room_id, limit)
    messages = _apply_clear_filter(
        db, current_user["user_id"], "room", room_id, messages
    )
    return _enrich_with_reactions(db, messages)


# ── Edit & delete endpoints ─────────────────────────────────────────


@router.patch(
    "/edit/{message_id}",
    responses={404: {"description": "Message not found or not owned by you"}},
)
def edit_message(
    message_id: str,
    body: EditMessageBody,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Edit a message's content. Only the original sender can edit.

    Returns 404 if the message doesn't exist, is already deleted,
    or does not belong to the authenticated user.
    """
    success = message_dal.edit_message(
        db, message_id, current_user["user_id"], body.content
    )
    if not success:
        raise HTTPException(
            status_code=404, detail="Message not found or not owned by you"
        )
    return {"edited": True}


@router.delete(
    "/delete/{message_id}",
    responses={404: {"description": "Message not found or not owned by you"}},
)
def delete_message(
    message_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Soft-delete a message. Only the original sender can delete.

    The message content is replaced with "[deleted]" and is_deleted is set to true.
    Returns 404 if the message doesn't exist, is already deleted,
    or does not belong to the authenticated user.
    """
    success = message_dal.soft_delete_message(db, message_id, current_user["user_id"])
    if not success:
        raise HTTPException(
            status_code=404, detail="Message not found or not owned by you"
        )
    return {"deleted": True}


# ── Reactions endpoint ──────────────────────────────────────────────


@router.get("/{message_id}/reactions")
def get_message_reactions(
    message_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return all reactions for a specific message."""
    reactions = reaction_dal.get_reactions_for_message(db, message_id)
    return [
        {"emoji": r.emoji, "username": r.username, "user_id": r.user_id}
        for r in reactions
    ]


# ── Link preview endpoint ──────────────────────────────────────────


@router.get(
    "/preview",
    responses={
        400: {"description": "Invalid URL: must start with http:// or https://"},
        404: {"description": "Could not generate preview"},
    },
)
async def get_link_preview(
    url: Annotated[str, Query(..., min_length=10, max_length=2048)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Fetch link preview metadata (Open Graph) for a URL.

    Returns title, description, image URL, and the original URL.
    Results are cached in Redis for 1 hour to avoid re-fetching.
    """
    # Validate URL scheme — only http/https allowed
    if not url.startswith(
        ("http://", "https://")  # NOSONAR
    ):
        raise HTTPException(
            status_code=400, detail="Invalid URL: must start with http:// or https://"
        )

    redis_client = get_redis()

    # Check cache first
    cached = await get_cached_preview(redis_client, url)
    if cached is not None:
        if cached.get("_miss"):
            raise HTTPException(status_code=404, detail="Could not generate preview")
        return cached

    # Fetch and cache
    preview = await fetch_preview(url)
    await cache_preview(redis_client, url, preview)

    if not preview:
        raise HTTPException(status_code=404, detail="Could not generate preview")
    return preview


# ── Private helpers ─────────────────────────────────────────────────


def _apply_clear_filter(
    db: Session,
    user_id: int,
    context_type: str,
    context_id: int,
    messages: list[MessageResponse],
) -> list[MessageResponse]:
    """Filter out messages that were sent before the user's clear timestamp.

    If the user has not cleared this context, returns all messages unchanged.
    """
    cleared_at = clear_dal.get_clear(db, user_id, context_type, context_id)
    if cleared_at is None:
        return messages

    return [m for m in messages if m.sent_at > cleared_at]


def _enrich_with_reactions(db: Session, messages: list[MessageResponse]) -> list[dict]:
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
