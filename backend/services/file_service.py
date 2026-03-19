# services/file_service.py — Business logic for file operations
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS
from dal import file_dal
from logging_config import get_logger
import models
import schemas

logger = get_logger("services.file")


async def save_file(file: UploadFile, sender_id: int, room_id: int, db: Session) -> models.File:
    # Validate file extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("file_type_rejected", extension=ext, filename=file.filename)
        raise HTTPException(400, f"File type '{ext}' is not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        logger.warning("file_too_large", size=len(content), filename=file.filename)
        raise HTTPException(413, "File exceeds maximum size of 150 MB")
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)
    logger.info("file_uploaded", filename=file.filename, size=len(content), room_id=room_id)
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
