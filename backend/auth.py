# auth.py — Authentication utilities (password hashing, JWT, FastAPI dependencies)
from datetime import datetime, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from dal import user_dal
from database import get_db
import models

ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        ph.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, db: Session) -> Optional[models.User]:
    """Decode a JWT token and return the user, or None if invalid/expired.
    Single source of truth — used by HTTP deps and WebSocket auth alike."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        user_id = int(sub)
        return user_dal.get_by_id(db, user_id)
    except (JWTError, ValueError):
        return None


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    user = decode_token(token, db)
    if user is None:
        raise _credentials_exception
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_global_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_current_user_flexible(request: Request, db: Session = Depends(get_db)) -> models.User:
    """Accept token from ?token= query param OR Authorization: Bearer header.
    Used by file download endpoint so browser <a href> links work."""
    auth_token = request.query_params.get("token")
    if not auth_token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            auth_token = auth[7:]
    if not auth_token:
        raise _credentials_exception
    user = decode_token(auth_token, db)
    if user is None:
        raise _credentials_exception
    return user
