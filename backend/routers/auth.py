# routers/auth.py — Thin controller for registration, login, logout, ping
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from services import auth_service
from ws_manager import manager
import models, schemas

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: schemas.UserRegister, db: Session = Depends(get_db)):
    return auth_service.register(db, body)


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    return auth_service.login(db, body, manager)


@router.post("/logout")
def logout(current_user: models.User = Depends(get_current_user)):
    return auth_service.logout(current_user.username, manager)


@router.post("/ping")
def ping(current_user: models.User = Depends(get_current_user)):
    """Re-register user as logged-in. Called on app load to survive server restarts."""
    return auth_service.ping(current_user.username, manager)
