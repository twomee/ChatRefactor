# app/routers/messages.py — Message replay, history, edit, delete, and reaction API
#
# CQRS READ side: these endpoints read from the messages database that is populated
# by the Kafka consumer (WRITE side). Both endpoints require JWT authentication.
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
from app.infrastructure.redis_client import get_redis
from app.schemas.message import MessageResponse, MessageWithReactionsResponse
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
    room_id: Annotated[
        int,
        Query(
            ...,
            description="Room ID to search within — required to prevent cross-room enumeration",
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
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
    """
    messages = message_service.get_replay_messages(db, room_id, since, limit)
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
    """
    messages = message_service.get_room_history(db, room_id, limit)
    return _enrich_with_reactions(db, messages)


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
