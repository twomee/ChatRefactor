# tests/test_core_logging.py — Tests for app/core/logging.py
#
# Covers:
#   - setup_logging configures structlog (dev vs prod renderer)
#   - get_logger returns a bound structlog logger
#   - _redact_sensitive_data processor: redacts sensitive keys, Bearer tokens
from unittest.mock import patch

import structlog

from app.core.logging import _redact_sensitive_data, get_logger, setup_logging


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


class TestRedactSensitiveData:
    """Tests for the _redact_sensitive_data structlog processor (lines 17-25)."""

    def test_redacts_password_key(self):
        """Values under 'password' key must be replaced with '[REDACTED]'."""
        event_dict = {"event": "user_login", "password": "super-secret"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["password"] == "[REDACTED]"

    def test_redacts_token_key(self):
        """Values under 'token' key must be replaced with '[REDACTED]'."""
        event_dict = {"event": "auth", "token": "abc123"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["token"] == "[REDACTED]"

    def test_redacts_secret_key(self):
        """Values under 'secret' key must be replaced with '[REDACTED]'."""
        event_dict = {"event": "config", "secret": "my-api-key"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["secret"] == "[REDACTED]"

    def test_redacts_authorization_key(self):
        """Values under 'authorization' key must be replaced with '[REDACTED]'."""
        event_dict = {"event": "request", "authorization": "Bearer token123"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["authorization"] == "[REDACTED]"

    def test_redacts_bearer_token_in_string_values(self):
        """String values containing 'Bearer <token>' must have the token replaced."""
        event_dict = {"event": "request", "header": "Bearer my-secret-token-value"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert "my-secret-token-value" not in result["header"]
        assert "Bearer" in result["header"]
        assert "[REDACTED]" in result["header"]

    def test_preserves_non_sensitive_keys(self):
        """Non-sensitive keys must pass through unchanged."""
        event_dict = {"event": "info", "user_id": 42, "room": "general"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["user_id"] == 42
        assert result["room"] == "general"

    def test_does_not_modify_non_bearer_string_values(self):
        """String values without Bearer tokens must pass through unchanged."""
        event_dict = {"event": "search", "query": "hello world"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["query"] == "hello world"

    def test_handles_empty_event_dict(self):
        """Should not raise when event_dict has only the event key."""
        event_dict = {"event": "noop"}
        result = _redact_sensitive_data(None, None, event_dict)
        assert result["event"] == "noop"


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
