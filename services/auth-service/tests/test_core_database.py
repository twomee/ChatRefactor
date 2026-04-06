# tests/test_core_database.py — Unit tests for app/core/database.py
"""
Tests for:
- get_db generator yields a session and closes it
"""

from unittest.mock import MagicMock, patch


class TestGetDb:
    """Tests for the get_db dependency generator."""

    def test_get_db_yields_session_and_closes(self):
        """get_db should yield a session and close it after the block exits."""
        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("app.core.database.SessionLocal", mock_session_local):
            from app.core.database import get_db

            gen = get_db()
            db = next(gen)

            assert db is mock_session

            # Exhaust the generator
            try:
                next(gen)
            except StopIteration:
                pass

            mock_session.close.assert_called_once()

    def test_get_db_closes_session_on_exception(self):
        """get_db should close the session even if an exception occurs."""
        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("app.core.database.SessionLocal", mock_session_local):
            from app.core.database import get_db

            gen = get_db()
            db = next(gen)

            # Simulate an error in the request handler
            try:
                gen.throw(ValueError("request error"))
            except ValueError:
                pass

            mock_session.close.assert_called_once()
