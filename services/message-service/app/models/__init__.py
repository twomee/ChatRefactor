# app/models/__init__.py — Message model
#
# Key difference from monolith: NO ForeignKey constraints.
# In the microservice architecture, users and rooms live in separate databases
# (auth-service and chat-service respectively). sender_id, recipient_id, and
# room_id are plain integers — referential integrity is enforced at the
# application level, not the database level.
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(
        String(36), unique=True, nullable=True, index=True
    )  # UUID for idempotent writes
    sender_id = Column(Integer, nullable=False)  # no FK — users in different DB
    sender_name = Column(String(64), nullable=True)  # denormalized for history display
    room_id = Column(
        Integer, nullable=True
    )  # null = private message, no FK — rooms in different DB
    recipient_id = Column(Integer, nullable=True)  # set for private messages, no FK
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    edited_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
