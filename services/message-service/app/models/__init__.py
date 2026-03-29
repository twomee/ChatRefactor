# app/models/__init__.py — Message & Reaction models
#
# Key difference from monolith: NO ForeignKey constraints.
# In the microservice architecture, users and rooms live in separate databases
# (auth-service and chat-service respectively). sender_id, recipient_id, and
# room_id are plain integers — referential integrity is enforced at the
# application level, not the database level.
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import UserDefinedType

from app.core.database import Base


class TSVector(UserDefinedType):
    """PostgreSQL tsvector type.

    Falls back to TEXT on databases that don't support tsvector (e.g. SQLite
    in tests). This lets the ORM model stay portable while the real FTS
    functionality is PostgreSQL-specific (migration + trigger).
    """

    cache_ok = True

    def get_col_spec(self):
        return "TSVECTOR"


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
    search_vector = Column(TSVector, nullable=True)  # populated by PG trigger


class Reaction(Base):
    """Emoji reaction on a message.

    Each row represents one user's reaction (one emoji) on one message.
    The unique constraint prevents duplicate reactions — a user can only
    react once per emoji per message.
    """

    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(64), nullable=False)
    emoji = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "emoji", name="uq_reaction_per_user_per_emoji"
        ),
    )
