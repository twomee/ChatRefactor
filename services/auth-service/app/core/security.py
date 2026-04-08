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
import jwt
from jwt.exceptions import PyJWTError

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
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        hours=ACCESS_TOKEN_EXPIRE_HOURS
    )
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

        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            return None
        if user_id <= 0:
            return None

        return {
            "user_id": user_id,
            "username": payload.get("username", ""),
        }
    except (PyJWTError, ValueError):
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

    Admin status must be verified against the database because it can change after a token
    is issued (e.g., an admin grants or revokes another user's admin status). Adding
    `is_admin` to the JWT payload would be stale within the token's lifetime.

    Usage: inject `db: Session` alongside this dependency and call `user_dal.get_by_id()`
    to verify `user.is_global_admin`. Example:

        @router.get("/admin/users")
        def list_users(
            current_user: dict = Depends(get_current_user),
            db: Session = Depends(get_db),
        ):
            user = user_dal.get_by_id(db, current_user["user_id"])
            if not user or not user.is_global_admin:
                raise HTTPException(status_code=403, detail="Admin access required")
            ...

    This function is intentionally not used as a FastAPI dependency directly — it would
    require a `db` parameter that security.py should not import (circular dependency risk).
    Admin authorization is handled inline in each admin route.
    """
    # NOTE: This function is a documented pattern guide, not a callable dependency.
    # Admin routes perform their own DB-backed check. See routers/auth.py for examples.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )
