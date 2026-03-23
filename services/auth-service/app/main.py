# app/main.py — FastAPI application entry point for the Auth Service
"""
Lifespan:
  Startup: seed admin user, start Kafka producer.
  Shutdown: stop Kafka producer.

Database schema is created by the db-init container (not on startup).

Includes:
  - Auth router (register, login, logout, ping, internal user lookups)
  - CorrelationIdMiddleware (request tracing via X-Request-ID)
  - Health endpoints (/health liveness, /ready readiness)
  - Global exception handler with structured logging
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import ADMIN_PASSWORD, ADMIN_USERNAME, APP_ENV, SECRET_KEY
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.dal import user_dal
from app.infrastructure.kafka_producer import (
    close_producer,
    init_producer,
    is_kafka_available,
)
from app.middleware.correlation import CorrelationIdMiddleware
from app.routers import auth

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the auth service."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("auth_service_starting", env=APP_ENV)

    # ── Security warnings ────────────────────────────────────────────
    if SECRET_KEY and "change-this-in-production" in SECRET_KEY:
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

    if ADMIN_PASSWORD == "changeme" and APP_ENV in ("staging", "prod"):
        logger.error(
            "INSECURE_ADMIN_PASSWORD",
            msg="ADMIN_PASSWORD is 'changeme'! Set a strong password via environment variable.",
        )

    # Seed admin user
    try:
        with Session(engine) as db:
            if ADMIN_USERNAME:
                admin_user = user_dal.get_by_username(db, ADMIN_USERNAME)
                if not admin_user:
                    user_dal.create(
                        db,
                        ADMIN_USERNAME,
                        hash_password(ADMIN_PASSWORD),
                        is_global_admin=True,
                    )
                    logger.info("admin_user_seeded", username=ADMIN_USERNAME)
                elif not admin_user.is_global_admin:
                    admin_user.is_global_admin = True
                    db.commit()
                    logger.info("admin_user_promoted", username=ADMIN_USERNAME)
    except Exception as e:
        logger.warning("admin_seed_skipped", error=str(e))

    # Start Kafka producer (gracefully degrades if Kafka is unavailable)
    await init_producer()

    logger.info("auth_service_started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("auth_service_shutting_down")
    await close_producer()
    logger.info("auth_service_shutdown_complete")


app = FastAPI(title="cHATBOX Auth Service", version="1.0.0", lifespan=lifespan)

# ── Middleware ──────────────────────────────────────────────────────────
app.add_middleware(CorrelationIdMiddleware)

# ── Routers ────────────────────────────────────────────────────────────
app.include_router(auth.router)


# ── Health checks ──────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health():
    """Liveness probe: returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready():
    """Readiness probe: verifies DB, Redis, and Kafka connectivity.

    DB and Redis are required — if either is down, returns 503.
    Kafka is optional — reports status but doesn't gate readiness.
    """
    checks = {}

    # Database check
    try:
        with Session(engine) as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    # Redis check
    try:
        from app.infrastructure.redis import get_redis

        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = str(e)

    # Kafka check (optional — doesn't gate readiness)
    try:
        checks["kafka"] = "ok" if is_kafka_available() else "degraded"
    except Exception as e:
        checks["kafka"] = f"degraded: {e}"

    # Only DB and Redis are required for readiness
    all_ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ok else "not_ready", **checks},
    )


# ── Global exception handler ──────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler: log the error and return a generic 500 response.

    Never leak internal error details to the client.
    """
    logger.error(
        "unhandled_exception", path=request.url.path, error=str(exc), exc_info=True
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
