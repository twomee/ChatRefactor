# services/auth_service.py — Business logic for registration, login, logout, ping
from fastapi import HTTPException
from sqlalchemy.orm import Session

import schemas
from core.config import ACCESS_TOKEN_EXPIRE_HOURS, APP_ENV
from core.logging import get_logger
from core.security import create_access_token, hash_password, verify_password
from dal import user_dal
from infrastructure.websocket import ConnectionManager

logger = get_logger("services.auth")


def register(db: Session, body: schemas.UserRegister) -> dict:
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Username and password required")
    if user_dal.get_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    user_dal.create(db, username=body.username.strip(), password_hash=hash_password(body.password))
    logger.info("user_registered", username=body.username.strip())
    return {"message": "Registered successfully"}


def login(db: Session, body: schemas.UserLogin, mgr: ConnectionManager) -> schemas.TokenResponse:
    user = user_dal.get_by_username(db, body.username)
    if not user or not verify_password(body.password, user.password_hash):
        logger.warning("login_failed", username=body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": str(user.id), "username": user.username})
    mgr.mark_logged_in(user.username)
    logger.info("user_logged_in", username=user.username)
    return schemas.TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )


def logout(username: str, mgr: ConnectionManager, token: str) -> dict:
    mgr.mark_logged_out(username)
    # Blacklist the token in Redis so it can't be reused
    try:
        from infrastructure.redis import get_redis

        r = get_redis()
        r.setex(f"blacklist:{token}", ACCESS_TOKEN_EXPIRE_HOURS * 3600, "1")
    except Exception as exc:
        # SECURITY: If Redis is down, we can't revoke the token.
        # Log at error level so ops teams are alerted.
        logger.error(
            "token_blacklist_failed", username=username, msg="Redis unavailable — token cannot be revoked until expiry"
        )
        if APP_ENV == "prod":
            raise HTTPException(
                status_code=503,
                detail="Logout partially failed — please try again or change your password",
            ) from exc
    logger.info("user_logged_out", username=username)
    return {"message": "Logged out"}


def ping(username: str, mgr: ConnectionManager) -> dict:
    mgr.mark_logged_in(username)
    return {"ok": True}
