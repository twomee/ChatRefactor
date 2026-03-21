# services/message_service.py — Business logic for chat messages
from sqlalchemy.orm import Session

import models
from dal import message_dal


def save_message(db: Session, sender_id: int, room_id: int, content: str) -> models.Message:
    return message_dal.create(db, sender_id, room_id, content)


def get_room_history(db: Session, room_id: int, limit: int = 50) -> list[dict]:
    """Return formatted message history for WebSocket delivery."""
    msgs = message_dal.get_room_history(db, room_id, limit)
    return [
        {
            "from": m.sender.username,
            "text": m.content,
            "timestamp": m.sent_at.isoformat(),
        }
        for m in msgs
    ]
