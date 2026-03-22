# tests/test_core_database.py — Tests for app/core/database.py
#
# Covers:
#   - get_db yields a working session
#   - get_db closes the session after use
#   - get_db closes the session even when an exception occurs
from unittest.mock import MagicMock, patch

from app.core.database import get_db


class TestGetDb:
    """Tests for the get_db dependency."""

    def test_yields_session(self):
        """get_db should yield a SQLAlchemy session."""
        mock_session = MagicMock()
        with patch("app.core.database.SessionLocal", return_value=mock_session):
            gen = get_db()
            session = next(gen)
            assert session is mock_session

            # Exhaust the generator
            try:
                next(gen)
            except StopIteration:
                pass

            mock_session.close.assert_called_once()

    def test_closes_session_on_exception(self):
        """get_db should close the session even if the caller raises an exception."""
        mock_session = MagicMock()
        with patch("app.core.database.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)

            # Simulate an exception during request handling
            try:
                gen.throw(ValueError("request failed"))
            except ValueError:
                pass

            mock_session.close.assert_called_once()

    def test_closes_session_on_normal_exit(self):
        """get_db should close the session on normal generator exhaustion."""
        mock_session = MagicMock()
        with patch("app.core.database.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)
            gen.close()

            mock_session.close.assert_called_once()
