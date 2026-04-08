# app/core/security.py — JWT validation for the message service
#
# Token validation is two-step:
#   1. decode_token() verifies the JWT signature and expiry (stateless, fast)
#   2. get_current_user() checks the Redis blacklist to reject revoked tokens
#
# The blacklist is written by the auth-service on logout. All services that accept
# Bearer tokens must check it to make logout effective across the whole platform.
#
# Fail behaviour:
#   - prod: Redis unavailable → reject token (fail closed)
#   - dev/staging: Redis unavailable → skip check (fail open for developer convenience)
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import ALGORITHM, APP_ENV, SECRET_KEY
from app.core.logging import get_logger
from app.infrastructure.redis_client import get_redis

_auth_logger = get_logger("security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def decode_token(token: str) -> dict | None:
    """Decode a JWT and return the payload as a dict, or None if invalid/expired.

    Stateless — only verifies signature and expiry. The caller is responsible for
    checking the Redis blacklist via get_current_user().
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        username = payload.get("username")
        if sub is None or username is None:
            return None
        return {"user_id": int(sub), "username": username}
    except (PyJWTError, ValueError):
        return None


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — validates JWT and checks Redis blacklist.

    Returns a dict with user_id and username from the JWT payload.
    Raises 401 if the token is invalid, expired, or has been revoked via logout.
    """
    user_info = decode_token(token)
    if user_info is None:
        raise _credentials_exception

    # Check Redis blacklist — rejects tokens revoked on logout by the auth-service
    redis_client = get_redis()
    if redis_client is not None:
        try:
            is_blacklisted = await redis_client.get(f"blacklist:{token}")
            if is_blacklisted:
                raise _credentials_exception
        except HTTPException:
            raise
        except Exception as exc:
            if APP_ENV == "prod":
                _auth_logger.error(
                    "redis_blacklist_unavailable",
                    msg="Rejecting token — cannot verify blacklist in production",
                    error=str(exc),
                )
                raise _credentials_exception
            _auth_logger.warning(
                "redis_blacklist_unavailable",
                msg="Redis down — skipping blacklist check (non-production)",
            )

    return user_info
