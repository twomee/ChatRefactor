# app/dal/message_dal.py — Data Access Layer for Message model
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Message


def create_idempotent(
    db: Session,
    message_id: str,
    sender_id: int,
    room_id: int | None,
    content: str,
    is_private: bool = False,
    recipient_id: int | None = None,
    sent_at: datetime | None = None,
    sender_name: str | None = None,
) -> bool:
    """Insert a message only if message_id doesn't already exist. Returns True if inserted."""
    existing = db.query(Message).filter(Message.message_id == message_id).first()
    if existing:
        return False

    msg = Message(
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        room_id=room_id,
        content=content,
        is_private=is_private,
        recipient_id=recipient_id,
    )
    if sent_at:
        msg.sent_at = sent_at
    db.add(msg)
    db.commit()
    return True


def get_by_room_since(
    db: Session, room_id: int, since: datetime, limit: int = 100
) -> list[Message]:
    """Return messages in a room since a given timestamp, for the replay API."""
    return (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
            Message.sent_at >= since,
        )
        .order_by(Message.sent_at.asc())
        .limit(limit)
        .all()
    )


def get_room_history(db: Session, room_id: int, limit: int = 50) -> list[Message]:
    """Return recent messages in a room, ordered oldest-first (for room join)."""
    msgs = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
        )
        .order_by(Message.sent_at.desc())
        .limit(limit)
        .all()
    )
    msgs.reverse()
    return msgs


def delete_all(db: Session):
    """Delete all messages. Used in tests only."""
    db.query(Message).delete()
    db.commit()
