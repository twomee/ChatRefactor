# services/auth_service.py — Business logic for registration and login
from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth import hash_password, verify_password, create_access_token
from dal import user_dal
import schemas


def register(db: Session, body: schemas.UserRegister) -> dict:
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Username and password required")
    if user_dal.get_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    user_dal.create(db, username=body.username.strip(), password_hash=hash_password(body.password))
    return {"message": "Registered successfully"}


def login(db: Session, body: schemas.UserLogin) -> schemas.TokenResponse:
    user = user_dal.get_by_username(db, body.username)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": str(user.id), "username": user.username})
    return schemas.TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )
