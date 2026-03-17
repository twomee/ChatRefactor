# models.py
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_global_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    uploaded_files = relationship("File", back_populates="sender")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    files = relationship("File", back_populates="room")
    messages = relationship("Message", back_populates="room")


class RoomAdmin(Base):
    """A row = user is admin in that room. Delete row to demote.
    Replaces the in-memory admins list + text file from chatServer.py."""
    __tablename__ = "room_admins"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    appointed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MutedUser(Base):
    """A row = user is muted in that room. Delete row to unmute.
    Replaces the in-memory _usersToMute list in chatServer.py."""
    __tablename__ = "muted_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    muted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class File(Base):
    """Replaces File.py + Files.py. Files are stored on disk; metadata here."""
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    original_name = Column(String(256), nullable=False)
    stored_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender = relationship("User", back_populates="uploaded_files")
    room = relationship("Room", back_populates="files")


class Message(Base):
    """New — the original app had no message persistence. Optional for v1."""
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)   # null = private message
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # set for private messages
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    room = relationship("Room", back_populates="messages")
