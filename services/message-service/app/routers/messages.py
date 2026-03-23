# app/routers/messages.py — Message replay and history API
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
from app.schemas.message import MessageResponse
from app.services import message_service

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/rooms/{room_id}", response_model=list[MessageResponse])
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
    return message_service.get_replay_messages(db, room_id, since, limit)


@router.get("/rooms/{room_id}/history", response_model=list[MessageResponse])
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
    return message_service.get_room_history(db, room_id, limit)
