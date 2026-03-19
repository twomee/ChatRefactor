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

from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD, CORS_ORIGINS, APP_ENV
from dal import user_dal, room_dal
from database import engine, Base
from logging_config import setup_logging, get_logger
from rate_limit import limiter
from routers import auth, rooms, files, admin, websocket, pm
from ws_manager import manager

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown logic for the application."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("app_starting", env=APP_ENV)

    if APP_ENV in ("staging", "prod"):
        try:
            from alembic.config import Config
            from alembic import command
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            logger.info("alembic_migrations_applied")
        except Exception:
            logger.warning("alembic_unavailable", msg="Falling back to create_all")
            Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

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

    logger.info("app_started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("app_shutting_down")

    if subscriber_task:
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

    # Close all room WebSocket connections gracefully
    for room_id, sockets in list(manager.rooms.items()):
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

# ── Middleware ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        from redis_client import get_redis
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = str(e)

    all_ok = all(v == "ok" for v in checks.values())
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
