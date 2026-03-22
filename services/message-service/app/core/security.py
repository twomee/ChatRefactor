# app/core/security.py — JWT validation for the message service
#
# Key difference from monolith: decode_token does NOT look up the user in the database.
# In a microservice world, the JWT payload contains enough info (sub=user_id, username).
# Other services validate tokens by decoding the JWT and trusting its payload, not by
# querying the auth DB. This makes token validation stateless and avoids cross-service
# DB calls.
#
# get_current_user returns a dict (not a User ORM object) with the JWT claims.
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.logging import get_logger

_auth_logger = get_logger("security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def decode_token(token: str) -> dict | None:
    """
    Decode a JWT and return the payload as a dict, or None if invalid/expired.

    Does NOT perform a database lookup. In a microservice architecture, the JWT payload
    (sub, username, etc.) is sufficient for authorization. This keeps token validation
    stateless and fast.

    No Redis blacklist check — the message service is a downstream consumer and does not
    manage token revocation. The auth service handles that.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")
        if user_id is None or username is None:
            return None
        return payload
    except JWTError:
        return None


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency — extracts and validates the current user from the Bearer token.

    Returns a dict with user_id and username from the JWT payload, NOT a User ORM object.
    This avoids a DB lookup on every authenticated request.
    """
    payload = decode_token(token)
    if payload is None:
        raise _credentials_exception
    return {"user_id": int(payload["sub"]), "username": payload["username"]}
