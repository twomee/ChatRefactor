# main.py
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from core.config import ADMIN_PASSWORD, ADMIN_USERNAME, APP_ENV, CORS_ORIGINS, SECRET_KEY
from core.database import engine
from core.logging import get_logger, setup_logging
from core.security import hash_password
from dal import room_dal, user_dal
from infrastructure.websocket import manager
from middleware.rate_limit import limiter
from middleware.security_headers import SecurityHeadersMiddleware
from routers import admin, auth, files, messages, pm, rooms, websocket

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown logic for the application."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("app_starting", env=APP_ENV)

    # ── Security warnings ────────────────────────────────────────────
    if "change-this-in-production" in SECRET_KEY:
        if APP_ENV in ("staging", "prod"):
            logger.error(
                "INSECURE_SECRET_KEY",
                msg="⚠️  SECRET_KEY is set to the default value! "
                "Set a strong SECRET_KEY via environment variable before deploying.",
            )
        else:
            logger.warning("default_secret_key", msg="Using default SECRET_KEY (acceptable for dev only)")

    if ADMIN_PASSWORD == "changeme" and APP_ENV in ("staging", "prod"):
        logger.error(
            "INSECURE_ADMIN_PASSWORD",
            msg="⚠️  ADMIN_PASSWORD is 'changeme'! Set a strong password via environment variable before deploying.",
        )

    # Run Alembic migrations to ensure schema is up to date
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_command.upgrade(alembic_cfg, "head")
    logger.info("alembic_migrations_applied")

    # Seed default rooms and admin user
    with Session(engine) as db:
        for room_name in ["politics", "sports", "movies"]:
            if not room_dal.get_by_name(db, room_name):
                room_dal.create(db, room_name)

        admin_user = user_dal.get_by_username(db, ADMIN_USERNAME)
        if not admin_user:
            user_dal.create(db, ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), is_global_admin=True)
        elif not admin_user.is_global_admin:
            admin_user.is_global_admin = True
            db.commit()

    # Start Redis subscriber for cross-worker WebSocket relay
    subscriber_task = None
    try:
        subscriber_task = asyncio.create_task(manager.start_subscriber())
    except Exception:
        logger.warning("redis_subscriber_failed_to_start")

    # Start Kafka producer + topics + consumer (gracefully degrades if Kafka unavailable)
    from infrastructure.kafka.consumers import MessagePersistenceConsumer
    from infrastructure.kafka.producer import start_producer, stop_producer
    from infrastructure.kafka.topics import ensure_topics

    await start_producer()
    await ensure_topics()
    persistence_consumer = MessagePersistenceConsumer()
    try:
        await persistence_consumer.start()
    except Exception:
        logger.warning("kafka_consumer_failed_to_start")

    logger.info("app_started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("app_shutting_down")

    # Stop Kafka consumer + producer
    await persistence_consumer.stop()
    await stop_producer()

    if subscriber_task:
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

    # Close all room WebSocket connections gracefully
    for _room_id, sockets in list(manager.rooms.items()):
        for ws in list(sockets):
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass

    # Close all lobby WebSocket connections
    for ws in list(manager.lobby_sockets.keys()):
        try:
            await ws.close(code=1001, reason="Server shutting down")
        except Exception:
            pass

    logger.info("app_shutdown_complete")


app = FastAPI(title="cHATBOX API", version="2.0.0", lifespan=lifespan)


# ── Security headers middleware ──────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)


# ── CORS middleware ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "If-None-Match"],
)

# ── Rate limiting ────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Routers ──────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(websocket.router)
app.include_router(pm.router)
app.include_router(messages.router)


# ── Health checks ────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health():
    """Liveness probe: returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready():
    """Readiness probe: verifies DB and Redis connectivity."""
    checks = {}

    try:
        with Session(engine) as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    try:
        from infrastructure.redis import get_redis

        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = str(e)

    # Kafka is optional — report status but don't gate readiness on it
    try:
        from infrastructure.kafka.producer import is_kafka_available

        checks["kafka"] = "ok" if is_kafka_available() else "degraded (sync fallback)"
    except Exception as e:
        checks["kafka"] = f"degraded: {e}"

    # Only DB and Redis are required for readiness
    required_ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    all_ok = required_ok
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ok else "not_ready", **checks},
    )


# ── Global error handler ────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
