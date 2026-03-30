# tests/test_services_message_service.py — Tests for app/services/message_service.py
#
# Covers:
#   - get_replay_messages: delegates to DAL, returns MessageResponse list
#   - get_room_history: delegates to DAL, returns MessageResponse list
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models import Message
from app.schemas.message import MessageResponse
from app.services.message_service import get_replay_messages, get_room_history


def _make_message(
    id: int = 1,
    message_id: str = "msg-001",
    sender_id: int = 1,
    room_id: int = 1,
    content: str = "Hello",
    is_private: bool = False,
    is_deleted: bool = False,
    sent_at: datetime | None = None,
) -> Message:
    """Create a Message ORM object for testing."""
    msg = Message()
    msg.id = id
    msg.message_id = message_id
    msg.sender_id = sender_id
    msg.room_id = room_id
    msg.content = content
    msg.is_private = is_private
    msg.is_deleted = is_deleted
    msg.sent_at = sent_at or datetime(2025, 1, 1, 12, 0, 0)
    return msg


class TestGetReplayMessages:
    """Tests for the get_replay_messages service function."""

    def test_returns_list_of_message_responses(self):
        """Should return a list of MessageResponse objects from DAL results."""
        mock_db = MagicMock()
        messages = [
            _make_message(id=1, message_id="msg-001", content="First"),
            _make_message(id=2, message_id="msg-002", content="Second"),
        ]

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_by_room_since.return_value = messages
            since = datetime(2025, 1, 1, 0, 0, 0)

            result = get_replay_messages(mock_db, room_id=1, since=since, limit=100)

        assert len(result) == 2
        assert all(isinstance(r, MessageResponse) for r in result)
        assert result[0].content == "First"
        assert result[1].content == "Second"

    def test_passes_correct_args_to_dal(self):
        """Should pass room_id, since, and limit to the DAL."""
        mock_db = MagicMock()
        since = datetime(2025, 6, 15, 10, 0, 0)

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_by_room_since.return_value = []

            get_replay_messages(mock_db, room_id=42, since=since, limit=25)

            mock_dal.get_by_room_since.assert_called_once_with(mock_db, 42, since, 25)

    def test_returns_empty_list_when_no_messages(self):
        """Should return empty list when DAL returns no messages."""
        mock_db = MagicMock()

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_by_room_since.return_value = []

            result = get_replay_messages(
                mock_db, room_id=1, since=datetime(2025, 1, 1), limit=100
            )

        assert result == []

    def test_default_limit_is_100(self):
        """Should use default limit of 100 when not specified."""
        mock_db = MagicMock()
        since = datetime(2025, 1, 1)

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_by_room_since.return_value = []

            get_replay_messages(mock_db, room_id=1, since=since)

            mock_dal.get_by_room_since.assert_called_once_with(mock_db, 1, since, 100)


class TestGetRoomHistory:
    """Tests for the get_room_history service function."""

    def test_returns_list_of_message_responses(self):
        """Should return a list of MessageResponse objects from DAL results."""
        mock_db = MagicMock()
        messages = [
            _make_message(id=1, message_id="msg-001", content="Old"),
            _make_message(id=2, message_id="msg-002", content="New"),
        ]

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_room_history.return_value = messages

            result = get_room_history(mock_db, room_id=1, limit=50)

        assert len(result) == 2
        assert all(isinstance(r, MessageResponse) for r in result)
        assert result[0].content == "Old"
        assert result[1].content == "New"

    def test_passes_correct_args_to_dal(self):
        """Should pass room_id and limit to the DAL."""
        mock_db = MagicMock()

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_room_history.return_value = []

            get_room_history(mock_db, room_id=7, limit=30)

            mock_dal.get_room_history.assert_called_once_with(mock_db, 7, 30)

    def test_returns_empty_list_when_no_messages(self):
        """Should return empty list when DAL returns no messages."""
        mock_db = MagicMock()

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_room_history.return_value = []

            result = get_room_history(mock_db, room_id=999, limit=50)

        assert result == []

    def test_default_limit_is_50(self):
        """Should use default limit of 50 when not specified."""
        mock_db = MagicMock()

        with patch("app.services.message_service.message_dal") as mock_dal:
            mock_dal.get_room_history.return_value = []

            get_room_history(mock_db, room_id=1)

            mock_dal.get_room_history.assert_called_once_with(mock_db, 1, 50)
