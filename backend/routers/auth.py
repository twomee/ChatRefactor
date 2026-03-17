# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from auth import hash_password, verify_password, create_access_token
import models, schemas

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: schemas.UserRegister, db: Session = Depends(get_db)):
    # Old code: chatServer._register() checked shelve DB for duplicate username
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Username and password required")

    user = models.User(
        username=body.username.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registered successfully"}


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    # Old code: chatServer._login() checked shelve DB then compared hashed passwords
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": str(user.id), "username": user.username})
    return schemas.TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )
