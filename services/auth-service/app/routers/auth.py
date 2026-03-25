# app/routers/auth.py — Thin controller for auth endpoints
"""
Public routes: POST /auth/register, /auth/login, /auth/logout, /auth/ping
Internal routes: GET /auth/users/{user_id}, /auth/users/by-username/{username}

Key differences from monolith:
1. NO rate limiting decorator — Kong API Gateway handles rate limiting now.
2. NO ConnectionManager injection — presence managed by Chat Service.
3. Internal user lookup endpoints are NEW — used by other services for inter-service calls.
4. Service functions are async (for Kafka event production).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user, oauth2_scheme
from app.dal import user_dal
from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("routers.auth")


# ── Public endpoints ──────────────────────────────────────────────────────────


@router.post("/register", status_code=201)
async def register(body: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account."""
    return await auth_service.register(db, body)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and receive a JWT access token."""
    return await auth_service.login(db, body)


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: dict = Depends(get_current_user),
):
    """Revoke the current access token (blacklists it in Redis)."""
    return await auth_service.logout(current_user, token)


@router.post("/ping")
def ping(current_user: dict = Depends(get_current_user)):
    """Presence ping. In microservice architecture, this is a simple health signal."""
    return auth_service.ping()


# ── Internal endpoints (for inter-service communication) ──────────────────────
# NOTE: The by-username route MUST come before the {user_id} route.
# FastAPI matches routes top-to-bottom. If /users/{user_id} is first,
# a request to /users/by-username/alice will match {user_id}="by-username"
# and fail with a type validation error (string can't coerce to int).


@router.get("/users/by-username/{username}", response_model=UserResponse)
def get_user_by_username(username: str, db: Session = Depends(get_db)):
    """Internal: Look up a user by username. Used by other services."""
    user = user_dal.get_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """Internal: Look up a user by ID. Used by other services (Chat, File, etc.)."""
    user = user_dal.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
