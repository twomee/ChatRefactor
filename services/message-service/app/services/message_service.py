# app/services/message_service.py — Business logic for message REST endpoints
#
# Thin service layer that sits between routers and DAL. Currently straightforward,
# but this is where you'd add caching, enrichment (e.g. resolving sender_id to
# username), or cross-cutting concerns as the service evolves.
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.dal import message_dal
from app.schemas.message import MessageResponse

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
