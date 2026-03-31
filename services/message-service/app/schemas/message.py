# app/schemas/message.py — Pydantic schemas for message API requests and responses
from datetime import datetime

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Standard message response — used for replay and history endpoints."""

    id: int
    message_id: str | None = None
    sender_id: int
    sender_name: str | None = None
    room_id: int | None = None
    content: str
    is_private: bool
    sent_at: datetime
    edited_at: datetime | None = None
    is_deleted: bool = False
    is_file: bool = False
    file_id: int | None = None

    model_config = {"from_attributes": True}


class ReactionResponse(BaseModel):
    """A single emoji reaction on a message."""

    emoji: str
    username: str
    user_id: int


class MessageWithReactionsResponse(MessageResponse):
    """Message response enriched with emoji reactions."""

    reactions: list[ReactionResponse] = []


class MessageHistoryResponse(BaseModel):
    """Extended message response with sender_name resolved from sender_id.

    The sender_name field is best-effort: if the auth service is unavailable,
    it falls back to "User #{sender_id}".
    """

    id: int
    message_id: str | None = None
    sender_id: int
    sender_name: str
    room_id: int | None = None
    content: str
    is_private: bool
    sent_at: datetime
    edited_at: datetime | None = None
    is_deleted: bool = False

    model_config = {"from_attributes": True}


# ── Request schemas ─────────────────────────────────────────────────


class ClearHistoryRequest(BaseModel):
    """Request body for clearing conversation history."""

    context_type: str = Field(..., pattern="^(room|pm)$")
    context_id: int


class DeletePMConversationRequest(BaseModel):
    """Request body for deleting a PM conversation."""

    other_user_id: int
