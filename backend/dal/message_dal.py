# dal/message_dal.py — Data Access Layer for Message model
from sqlalchemy.orm import Session
import models


def create(db: Session, sender_id: int, room_id: int, content: str,
           is_private: bool = False, recipient_id: int | None = None) -> models.Message:
    msg = models.Message(
        sender_id=sender_id,
        room_id=room_id,
        content=content,
        is_private=is_private,
        recipient_id=recipient_id,
    )
    db.add(msg)
    db.commit()
    return msg


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


def delete_all(db: Session):
    db.query(models.Message).delete()
    db.commit()
