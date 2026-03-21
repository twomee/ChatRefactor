# dal/message_dal.py — Data Access Layer for Message model
from datetime import datetime

from sqlalchemy.orm import Session

import models


def create(
    db: Session,
    sender_id: int,
    room_id: int,
    content: str,
    is_private: bool = False,
    recipient_id: int | None = None,
    message_id: str | None = None,
    sent_at: datetime | None = None,
) -> models.Message:
    msg = models.Message(
        message_id=message_id,
        sender_id=sender_id,
        room_id=room_id,
        content=content,
        is_private=is_private,
        recipient_id=recipient_id,
    )
    if sent_at:
        msg.sent_at = sent_at
    db.add(msg)
    db.commit()
    return msg


def create_idempotent(
    db: Session,
    message_id: str,
    sender_id: int,
    room_id: int | None,
    content: str,
    is_private: bool = False,
    recipient_id: int | None = None,
    sent_at: datetime | None = None,
) -> bool:
    """Insert a message only if message_id doesn't already exist. Returns True if inserted."""
    existing = db.query(models.Message).filter(models.Message.message_id == message_id).first()
    if existing:
        return False
    msg = models.Message(
        message_id=message_id,
        sender_id=sender_id,
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


def get_room_history(db: Session, room_id: int, limit: int = 50) -> list[models.Message]:
    msgs = (
        db.query(models.Message)
        .filter(models.Message.room_id == room_id, models.Message.is_private == False)
        .order_by(models.Message.sent_at.desc())
        .limit(limit)
        .all()
    )
    msgs.reverse()
    return msgs


def get_by_room_since(db: Session, room_id: int, since: datetime, limit: int = 100) -> list[models.Message]:
    """Return messages in a room since a given timestamp, for the replay API."""
    return (
        db.query(models.Message)
        .filter(
            models.Message.room_id == room_id,
            models.Message.is_private == False,
            models.Message.sent_at >= since,
        )
        .order_by(models.Message.sent_at.asc())
        .limit(limit)
        .all()
    )


def delete_all(db: Session):
    db.query(models.Message).delete()
    db.commit()
