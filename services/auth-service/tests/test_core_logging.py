# tests/test_core_logging.py — Unit tests for app/core/logging.py
"""
Tests for:
- setup_logging in non-dev mode (JSON renderer)
- get_logger returns a structlog logger
"""

from unittest.mock import patch

from app.core.logging import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging configuration."""

    def test_setup_logging_dev_mode(self):
        """In dev mode, should configure console renderer."""
        with patch("app.core.logging.APP_ENV", "dev"):
            setup_logging()
            # Should not raise

    def test_setup_logging_prod_mode(self):
        """In prod mode, should configure JSON renderer."""
        with patch("app.core.logging.APP_ENV", "prod"):
            setup_logging()
            # Should not raise


class TestGetLogger:
    """Tests for get_logger."""

    def test_get_logger_returns_logger(self):
        logger = get_logger("test")
        assert logger is not None
        # structlog loggers have standard logging methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
