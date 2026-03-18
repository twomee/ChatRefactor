# dal/file_dal.py — Data Access Layer for File model
from sqlalchemy.orm import Session
import models


def create(db: Session, original_name: str, stored_path: str,
           file_size: int, sender_id: int, room_id: int) -> models.File:
    record = models.File(
        original_name=original_name,
        stored_path=stored_path,
        file_size=file_size,
        sender_id=sender_id,
        room_id=room_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_by_id(db: Session, file_id: int) -> models.File | None:
    return db.query(models.File).filter(models.File.id == file_id).first()


def list_by_room(db: Session, room_id: int) -> list[models.File]:
    return db.query(models.File).filter(models.File.room_id == room_id).all()
