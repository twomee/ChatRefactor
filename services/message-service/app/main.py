# app/main.py — Message Service entrypoint
#
# Lifespan:
#   Startup: run Alembic migrations, start Kafka consumer + producer.
#   Shutdown: stop Kafka consumer + producer.
#
# Includes:
#   - Messages router (replay and history endpoints)
#   - CorrelationIdMiddleware (request tracing via X-Request-ID)
#   - Health endpoints (/health liveness, /ready readiness)
#   - Global exception handler with structured logging
from contextlib import asynccontextmanager

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import APP_ENV, SECRET_KEY
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.infrastructure.kafka_producer import (
    close_producer,
    init_producer,
    is_kafka_available,
)
from app.middleware.correlation import CorrelationIdMiddleware
from app.routers import messages

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown logic for the message service."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("message_service_starting", env=APP_ENV)

    # ── Security warnings ────────────────────────────────────────────
    if "change-this-in-production" in SECRET_KEY:
        if APP_ENV in ("staging", "prod"):
            logger.error(
                "INSECURE_SECRET_KEY",
                msg="SECRET_KEY is set to the default value! "
                "Set a strong SECRET_KEY via environment variable before deploying.",
            )
        else:
            logger.warning(
                "default_secret_key",
                msg="Using default SECRET_KEY (acceptable for dev only)",
            )

    # Run Alembic migrations to ensure schema is up to date
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("alembic_migrations_applied")
    except Exception as e:
        logger.warning("alembic_migration_skipped", error=str(e))

    # Start Kafka producer (for DLQ)
    await init_producer()

    # Start Kafka consumer (persistence)
    from app.consumers.persistence_consumer import MessagePersistenceConsumer

    persistence_consumer = MessagePersistenceConsumer()
    try:
        await persistence_consumer.start()
    except Exception:
        logger.warning("kafka_consumer_failed_to_start")

    logger.info("message_service_started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("message_service_shutting_down")

    await persistence_consumer.stop()
    await close_producer()

    logger.info("message_service_shutdown_complete")


app = FastAPI(title="cHATBOX Message Service", version="1.0.0", lifespan=lifespan)

# ── Middleware ──────────────────────────────────────────────────────
app.add_middleware(CorrelationIdMiddleware)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(messages.router)


# ── Health checks ────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health():
    """Liveness probe: returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready():
    """
    Readiness probe: verifies DB and Kafka connectivity.

    DB is required — if it's down, returns 503.
    Kafka is optional — reports status but doesn't gate readiness.
    No Redis in the message service.
    """
    checks = {}

    # Database check (required)
    try:
        with Session(engine) as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    # Kafka check (optional — degraded is acceptable)
    try:
        checks["kafka"] = "ok" if is_kafka_available() else "degraded"
    except Exception as e:
        checks["kafka"] = f"degraded: {e}"

    # Only DB is required for readiness
    all_ok = checks.get("database") == "ok"
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ok else "not_ready", **checks},
    )


# ── Global error handler ────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler: log the error and return a generic 500 response."""
    logger.error(
        "unhandled_exception", path=request.url.path, error=str(exc), exc_info=True
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
