# app/routers/messages.py — Message replay, history, and reaction API
#
# CQRS READ side: these endpoints read from the messages database that is populated
# by the Kafka consumer (WRITE side). Both endpoints require JWT authentication.
#
# Key difference from monolith:
# - No room existence check (rooms live in a different service/database)
# - get_current_user returns a dict, not a User ORM object
# - Sender names are NOT resolved here (would require auth service call per message)
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.dal import reaction_dal
from app.schemas.message import MessageResponse, MessageWithReactionsResponse
from app.services import message_service

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/rooms/{room_id}", response_model=list[MessageWithReactionsResponse])
def get_room_messages(
    room_id: int,
    since: datetime = Query(
        ..., description="ISO 8601 timestamp — return messages after this time"
    ),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Replay endpoint: fetch messages in a room since a given timestamp.

    Use case: client reconnects after a disconnect, provides the timestamp of the
    last message it received, and gets everything it missed.
    """
    messages = message_service.get_replay_messages(db, room_id, since, limit)
    return _enrich_with_reactions(db, messages)


@router.get("/rooms/{room_id}/history", response_model=list[MessageWithReactionsResponse])
def get_room_history(
    room_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    History endpoint: fetch the most recent messages in a room.

    Use case: user joins a room and wants to see what was recently discussed.
    Returns messages in chronological order (oldest first).
    """
    messages = message_service.get_room_history(db, room_id, limit)
    return _enrich_with_reactions(db, messages)


@router.get("/{message_id}/reactions")
def get_message_reactions(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return all reactions for a specific message."""
    reactions = reaction_dal.get_reactions_for_message(db, message_id)
    return [
        {"emoji": r.emoji, "username": r.username, "user_id": r.user_id}
        for r in reactions
    ]


def _enrich_with_reactions(
    db: Session, messages: list[MessageResponse]
) -> list[dict]:
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
