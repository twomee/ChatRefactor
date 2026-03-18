# services/file_service.py — Business logic for file operations
import uuid

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES
from dal import file_dal
import models
import schemas


async def save_file(file: UploadFile, sender_id: int, room_id: int, db: Session) -> models.File:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, "File exceeds maximum size of 150 MB")
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)
    return file_dal.create(db, file.filename, str(dest), len(content), sender_id, room_id)


def get_file(db: Session, file_id: int) -> models.File:
    record = file_dal.get_by_id(db, file_id)
    if not record:
        raise HTTPException(404, "File not found")
    return record


def list_room_files(db: Session, room_id: int) -> list[schemas.FileResponse]:
    files = file_dal.list_by_room(db, room_id)
    return [
        schemas.FileResponse(
            id=f.id,
            original_name=f.original_name,
            file_size=f.file_size,
            sender=f.sender.username,
            room_id=f.room_id,
            uploaded_at=f.uploaded_at,
        ) for f in files
    ]
