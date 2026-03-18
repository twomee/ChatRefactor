# routers/auth.py — Thin controller for registration and login
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services import auth_service
import schemas

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: schemas.UserRegister, db: Session = Depends(get_db)):
    return auth_service.register(db, body)


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    return auth_service.login(db, body)
