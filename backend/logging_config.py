# logging_config.py — Structured logging setup using structlog
import logging
import structlog
from config import APP_ENV


def setup_logging():
    """Configure structlog with human-readable output in dev, JSON in prod."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if APP_ENV == "dev":
        renderer = structlog.dev.ConsoleRenderer()
        log_level = logging.DEBUG
    else:
        renderer = structlog.processors.JSONRenderer()
        log_level = logging.INFO

    structlog.configure(
        processors=shared_processors + [
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
