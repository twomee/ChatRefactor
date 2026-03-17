# services/file_service.py
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES
import models


async def save_file(file: UploadFile, sender_id: int, room_id: int, db: Session) -> models.File:
    # Check file size — old: chatServer checked size before sending, rejected if > 150MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, f"File exceeds maximum size of 150 MB")

    # Store with a unique name to prevent collisions — old: chatServer used _fileCount integer
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)

    file_record = models.File(
        original_name=file.filename,
        stored_path=str(dest),
        file_size=len(content),
        sender_id=sender_id,
        room_id=room_id,
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record
