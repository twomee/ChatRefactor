# app/core/security.py — Authentication utilities (password hashing, JWT, FastAPI dependencies)
"""
Key difference from monolith: decode_token does NOT look up the user in the database.
In a microservice world, the JWT payload contains enough info (sub=user_id, username).
Other services validate tokens by decoding the JWT and trusting its payload, not by
querying the auth DB. This makes token validation stateless and avoids cross-service
DB calls.

get_current_user returns a dict (not a User ORM object) with the JWT claims.
"""
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import ACCESS_TOKEN_EXPIRE_HOURS, ALGORITHM, APP_ENV, SECRET_KEY
from app.core.logging import get_logger

_auth_logger = get_logger("auth")

ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        ph.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(data: dict) -> str:
    """Create a JWT access token with an expiry claim."""
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode a JWT and return the payload as a dict, or None if invalid/expired/blacklisted.

    Does NOT perform a database lookup. In a microservice architecture, the JWT payload
    (sub, username, etc.) is sufficient for authorization. This keeps token validation
    stateless and fast.

    Checks the Redis blacklist to reject revoked tokens:
    - Production: fail closed (reject token if Redis is unreachable)
    - Dev/staging: fail open (allow token even if Redis is down)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check Redis blacklist (token revoked on logout)
        try:
            from app.infrastructure.redis import get_redis

            if get_redis().get(f"blacklist:{token}"):
                return None
        except Exception:
            if APP_ENV == "prod":
                _auth_logger.error(
                    "redis_blacklist_unavailable",
                    msg="Rejecting token — cannot verify blacklist in production",
                )
                return None
            _auth_logger.warning(
                "redis_blacklist_unavailable",
                msg="Redis down — skipping blacklist check (non-production)",
            )

        sub = payload.get("sub")
        if sub is None:
            return None

        return {
            "user_id": int(sub),
            "username": payload.get("username", ""),
        }
    except (JWTError, ValueError):
        return None


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — extracts and validates the current user from the Bearer token.

    Returns a dict with user_id and username from the JWT payload, NOT a User ORM object.
    This avoids a DB lookup on every authenticated request.
    """
    user_info = decode_token(token)
    if user_info is None:
        raise _credentials_exception
    return user_info


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — ensures the current user is a global admin.

    Note: In the microservice architecture, admin status is checked by looking up the user
    in the DB for admin-only endpoints. This is acceptable because admin endpoints are
    infrequent. For high-frequency endpoints, consider adding is_admin to the JWT claims.
    """
    # For admin check, we need to verify against the DB since admin status
    # could have changed since the token was issued
    from sqlalchemy.orm import Session

    from app.core.database import get_db
    from app.dal import user_dal

    # This is a workaround — in practice, admin-only routes will inject db separately
    # and check admin status. This dependency is kept for backward compatibility.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin verification requires database check — use route-level admin verification",
    )
