# routers/auth.py — Thin controller for registration, login, logout, ping
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import get_current_user, oauth2_scheme
from database import get_db
from logging_config import get_logger
from rate_limit import limiter
from services import auth_service
from ws_manager import manager
import models, schemas

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("routers.auth")


@router.post("/register", status_code=201)
@limiter.limit("5/minute")
def register(request: Request, body: schemas.UserRegister, db: Session = Depends(get_db)):
    result = auth_service.register(db, body)
    logger.info("user_registered", username=body.username)
    return result


@router.post("/login", response_model=schemas.TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: schemas.UserLogin, db: Session = Depends(get_db)):
    return auth_service.login(db, body, manager)


@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: models.User = Depends(get_current_user),
):
    logger.info("user_logout", username=current_user.username)
    return auth_service.logout(current_user.username, manager, token)


@router.post("/ping")
def ping(current_user: models.User = Depends(get_current_user)):
    """Re-register user as logged-in. Called on app load to survive server restarts."""
    return auth_service.ping(current_user.username, manager)
