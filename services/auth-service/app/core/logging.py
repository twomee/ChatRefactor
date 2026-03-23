# app/core/logging.py — Structured logging setup using structlog
import logging
import re

import structlog

from app.core.config import APP_ENV

# Keys whose values should be fully redacted in log output.
_REDACT_KEYS = {"password", "token", "secret", "secret_key", "authorization"}

# Pattern to detect Bearer tokens in string values.
_BEARER_PATTERN = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)


def _redact_sensitive_data(_logger, _method, event_dict):
    """Structlog processor that redacts sensitive fields from log events."""
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
        elif isinstance(event_dict[key], str) and _BEARER_PATTERN.search(event_dict[key]):
            event_dict[key] = _BEARER_PATTERN.sub(r"\1[REDACTED]", event_dict[key])
    return event_dict


def setup_logging():
    """Configure structlog with human-readable output in dev, JSON in prod."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_sensitive_data,
    ]

    if APP_ENV == "dev":
        renderer = structlog.dev.ConsoleRenderer()
        log_level = logging.DEBUG
    else:
        renderer = structlog.processors.JSONRenderer()
        log_level = logging.INFO

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)


def get_logger(name: str):
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)
