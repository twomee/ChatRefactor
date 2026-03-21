# services/file_service.py — Business logic for file operations
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from core.config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS
from dal import file_dal
from core.logging import get_logger
import models
import schemas

logger = get_logger("services.file")


async def save_file(file: UploadFile, sender_id: int, room_id: int, db: Session) -> models.File:
    # ── Sanitize filename ──────────────────────────────────────────────
    # Strip directory components to prevent path traversal (e.g., "../../etc/passwd")
    raw_name = file.filename or "unnamed"
    # Path.name strips all directory components; also remove any null bytes
    clean_name = Path(raw_name).name.replace("\x00", "")
    # Strip leading dots to prevent hidden files (e.g., ".env", "..secret")
    clean_name = clean_name.lstrip(".")
    if not clean_name:
        clean_name = "unnamed"

    # Validate file extension
    ext = Path(clean_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("file_type_rejected", extension=ext, filename=clean_name)
        raise HTTPException(400, f"File type '{ext}' is not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        logger.warning("file_too_large", size=len(content), filename=clean_name)
        raise HTTPException(413, "File exceeds maximum size of 150 MB")

    # Use UUID prefix to guarantee uniqueness; sanitized name for human readability
    safe_name = f"{uuid.uuid4().hex}_{clean_name}"
    dest = UPLOAD_DIR / safe_name

    # Final safety check: ensure the resolved path is still inside UPLOAD_DIR
    if not dest.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        logger.error("path_traversal_blocked", attempted_path=str(dest), filename=raw_name)
        raise HTTPException(400, "Invalid filename")

    dest.write_bytes(content)
    logger.info("file_uploaded", filename=clean_name, size=len(content), room_id=room_id)
    return file_dal.create(db, clean_name, str(dest), len(content), sender_id, room_id)


def get_file(db: Session, file_id: int) -> models.File:
    record = file_dal.get_by_id(db, file_id)
    if not record:
        raise HTTPException(404, "File not found")
    # SECURITY: Verify the stored path is inside UPLOAD_DIR to prevent serving arbitrary files
    stored = Path(record.stored_path).resolve()
    if not stored.is_relative_to(UPLOAD_DIR.resolve()):
        logger.error("path_traversal_on_download", file_id=file_id, stored_path=record.stored_path)
        raise HTTPException(403, "Access denied")
    if not stored.exists():
        logger.warning("file_missing_on_disk", file_id=file_id, stored_path=record.stored_path)
        raise HTTPException(404, "File not found on disk")
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
