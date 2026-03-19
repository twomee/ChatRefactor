# routers/messages.py — Message replay API
#
# Allows clients to fetch messages they may have missed (e.g., after reconnect,
# network blip, or page refresh) without re-joining the room.
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from dal import message_dal, room_dal
from database import get_db
import models
import schemas

router = APIRouter(prefix="/rooms", tags=["messages"])


@router.get("/{room_id}/messages", response_model=list[schemas.MessageResponse])
def get_room_messages(
    room_id: int,
    since: datetime = Query(..., description="ISO 8601 timestamp — return messages after this time"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Replay endpoint: fetch messages in a room since a given timestamp.

    Use case: client reconnects after a disconnect, provides the timestamp of the
    last message it received, and gets everything it missed.
    """
    room = room_dal.get_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    messages = message_dal.get_by_room_since(db, room_id, since, limit)
    return [
        schemas.MessageResponse(
            id=m.id,
            message_id=m.message_id,
            sender=m.sender.username,
            room_id=m.room_id,
            content=m.content,
            is_private=m.is_private,
            sent_at=m.sent_at,
        )
        for m in messages
    ]
