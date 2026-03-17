# routers/files.py
from fastapi import APIRouter, Depends, Request, UploadFile, File as FastAPIFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from auth import get_current_user, get_current_user_flexible
from services.file_service import save_file
from ws_manager import manager
import models, schemas

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=schemas.FileResponse)
async def upload_file(
    room_id: int,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    file_record = await save_file(file, current_user.id, room_id, db)

    # Notify all users in the room that a file is available — old: server sent 'filename:' message
    await manager.broadcast(room_id, {
        "type": "file_shared",
        "file_id": file_record.id,
        "filename": file_record.original_name,
        "size": file_record.file_size,
        "from": current_user.username,
        "room_id": room_id,
    })

    return schemas.FileResponse(
        id=file_record.id,
        original_name=file_record.original_name,
        file_size=file_record.file_size,
        sender=current_user.username,
        room_id=room_id,
        uploaded_at=file_record.uploaded_at,
    )


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user_flexible),
):
    # Old: chatServer._serverSendFile() sent raw bytes over socket
    record = db.query(models.File).filter(models.File.id == file_id).first()
    if not record:
        raise HTTPException(404, "File not found")
    return FileResponse(
        path=record.stored_path,
        filename=record.original_name,
        media_type="application/octet-stream",
    )


@router.get("/room/{room_id}", response_model=List[schemas.FileResponse])
def list_room_files(room_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    files = db.query(models.File).filter(models.File.room_id == room_id).all()
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
