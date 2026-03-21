# dal/user_dal.py — Data Access Layer for User model
from sqlalchemy.orm import Session

import models


def get_by_id(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def create(db: Session, username: str, password_hash: str, is_global_admin: bool = False) -> models.User:
    user = models.User(username=username, password_hash=password_hash, is_global_admin=is_global_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_all(db: Session):
    db.query(models.User).delete()
    db.commit()
