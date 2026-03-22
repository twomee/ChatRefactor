# tests/test_schemas_message.py — Tests for app/schemas/message.py
#
# Covers:
#   - MessageResponse: validates from ORM, required/optional fields, from_attributes
#   - MessageHistoryResponse: validates with sender_name field
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.message import MessageHistoryResponse, MessageResponse


class TestMessageResponse:
    """Tests for the MessageResponse Pydantic schema."""

    def test_valid_message_response(self):
        """Should create a valid MessageResponse with all fields."""
        data = {
            "id": 1,
            "message_id": "msg-001",
            "sender_id": 42,
            "room_id": 1,
            "content": "Hello, world!",
            "is_private": False,
            "sent_at": datetime(2025, 1, 1, 12, 0, 0),
        }
        msg = MessageResponse(**data)

        assert msg.id == 1
        assert msg.message_id == "msg-001"
        assert msg.sender_id == 42
        assert msg.room_id == 1
        assert msg.content == "Hello, world!"
        assert msg.is_private is False
        assert msg.sent_at == datetime(2025, 1, 1, 12, 0, 0)

    def test_message_response_optional_fields(self):
        """message_id and room_id should be optional (None allowed)."""
        data = {
            "id": 1,
            "message_id": None,
            "sender_id": 42,
            "room_id": None,
            "content": "Private message",
            "is_private": True,
            "sent_at": datetime(2025, 1, 1, 12, 0, 0),
        }
        msg = MessageResponse(**data)

        assert msg.message_id is None
        assert msg.room_id is None

    def test_message_response_missing_required_field(self):
        """Should raise ValidationError when required field is missing."""
        data = {
            "id": 1,
            "sender_id": 42,
            # missing content
            "is_private": False,
            "sent_at": datetime(2025, 1, 1, 12, 0, 0),
        }
        with pytest.raises(ValidationError):
            MessageResponse(**data)

    def test_message_response_from_attributes(self):
        """Should be able to create from an ORM-like object using model_validate."""

        class FakeMessage:
            id = 1
            message_id = "msg-orm"
            sender_id = 10
            room_id = 5
            content = "From ORM"
            is_private = False
            sent_at = datetime(2025, 3, 15, 8, 0, 0)

        msg = MessageResponse.model_validate(FakeMessage())

        assert msg.id == 1
        assert msg.message_id == "msg-orm"
        assert msg.content == "From ORM"


class TestMessageHistoryResponse:
    """Tests for the MessageHistoryResponse Pydantic schema."""

    def test_valid_history_response(self):
        """Should create a valid MessageHistoryResponse with sender_name."""
        data = {
            "id": 1,
            "message_id": "msg-001",
            "sender_id": 42,
            "sender_name": "alice",
            "room_id": 1,
            "content": "Hello!",
            "is_private": False,
            "sent_at": datetime(2025, 1, 1, 12, 0, 0),
        }
        msg = MessageHistoryResponse(**data)

        assert msg.sender_name == "alice"
        assert msg.content == "Hello!"

    def test_history_response_requires_sender_name(self):
        """Should raise ValidationError when sender_name is missing."""
        data = {
            "id": 1,
            "message_id": "msg-001",
            "sender_id": 42,
            # missing sender_name
            "room_id": 1,
            "content": "Hello!",
            "is_private": False,
            "sent_at": datetime(2025, 1, 1, 12, 0, 0),
        }
        with pytest.raises(ValidationError):
            MessageHistoryResponse(**data)

    def test_history_response_from_attributes(self):
        """Should be able to create from an ORM-like object using model_validate."""

        class FakeHistoryMessage:
            id = 2
            message_id = "msg-hist"
            sender_id = 10
            sender_name = "bob"
            room_id = 5
            content = "History message"
            is_private = False
            sent_at = datetime(2025, 6, 1, 9, 0, 0)

        msg = MessageHistoryResponse.model_validate(FakeHistoryMessage())

        assert msg.sender_name == "bob"
        assert msg.content == "History message"
