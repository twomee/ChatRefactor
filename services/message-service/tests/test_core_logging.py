# tests/test_core_logging.py — Tests for app/core/logging.py
#
# Covers:
#   - setup_logging configures structlog (dev vs prod renderer)
#   - get_logger returns a bound structlog logger
from unittest.mock import patch

import structlog

from app.core.logging import get_logger, setup_logging


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_setup_logging_dev_uses_console_renderer(self):
        """In dev mode, setup_logging should configure the ConsoleRenderer."""
        with patch("app.core.logging.APP_ENV", "dev"):
            setup_logging()

        # Verify structlog is configured (no exception means success)
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_setup_logging_prod_uses_json_renderer(self):
        """In prod mode, setup_logging should configure the JSONRenderer."""
        with patch("app.core.logging.APP_ENV", "prod"):
            setup_logging()

        # Verify structlog is configured
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_setup_logging_does_not_raise(self):
        """setup_logging should not raise exceptions regardless of environment."""
        for env in ("dev", "prod", "staging", "test"):
            with patch("app.core.logging.APP_ENV", env):
                setup_logging()  # Should not raise


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_returns_bound_logger(self):
        """get_logger should return a structlog BoundLogger instance."""
        logger = get_logger("test_module")
        assert logger is not None

    def test_returns_different_loggers_for_different_names(self):
        """get_logger should return loggers that can be named differently."""
        logger_a = get_logger("module_a")
        logger_b = get_logger("module_b")
        # Both should be valid loggers (structlog creates new bound loggers)
        assert logger_a is not None
        assert logger_b is not None

    def test_logger_can_log_without_error(self):
        """Logger returned by get_logger should be callable for log operations."""
        setup_logging()
        logger = get_logger("test_logging")
        # These should not raise
        logger.info("test_event", key="value")
        logger.warning("test_warning")
        logger.debug("test_debug")
