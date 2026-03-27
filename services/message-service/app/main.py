# app/main.py — Message Service entrypoint
#
# Lifespan:
#   Startup: start Kafka consumer + producer.
#   Shutdown: stop Kafka consumer + producer.
#
# Database schema is created by the db-init container (not on startup).
#
# Includes:
#   - Messages router (replay and history endpoints)
#   - CorrelationIdMiddleware (request tracing via X-Request-ID)
#   - Health endpoints (/health liveness, /ready readiness)
#   - Global exception handler with structured logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import APP_ENV, SECRET_KEY
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.infrastructure.metrics import db_pool_checked_out, db_pool_size
from app.infrastructure.kafka_producer import (
    close_producer,
    init_producer,
    is_kafka_available,
)
from app.middleware.correlation import CorrelationIdMiddleware
from app.routers import messages
from prometheus_fastapi_instrumentator import Instrumentator

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

    # Start Kafka producer (for DLQ)
    await init_producer()

    # Start Kafka consumer (persistence)
    # Topics are auto-created by Kafka when auto.create.topics.enable=true (default)
    from app.consumers.persistence_consumer import MessagePersistenceConsumer

    persistence_consumer = MessagePersistenceConsumer()
    try:
        await persistence_consumer.start()
    except Exception:
        logger.warning("kafka_consumer_failed_to_start")

    # Background task: periodically update DB pool gauges for Prometheus
    async def _collect_pool_stats():
        while True:
            try:
                pool = engine.pool
                db_pool_size.set(pool.size())
                db_pool_checked_out.set(pool.checkedout())
            except Exception:
                pass
            await asyncio.sleep(15)

    pool_stats_task = asyncio.create_task(_collect_pool_stats())

    logger.info("message_service_started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("message_service_shutting_down")

    pool_stats_task.cancel()
    try:
        await pool_stats_task
    except asyncio.CancelledError:
        pass

    await persistence_consumer.stop()
    await close_producer()

    logger.info("message_service_shutdown_complete")


app = FastAPI(title="cHATBOX Message Service", version="1.0.0", lifespan=lifespan)

# ── Prometheus metrics ────────────────────────────────────────────────
instrumentator = Instrumentator(
    excluded_handlers=["/health", "/ready", "/metrics"],
)
instrumentator.instrument(app).expose(app, include_in_schema=False)

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
