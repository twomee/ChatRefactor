# routers/rooms.py — Thin controller for room listing and creation
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from auth import get_current_user, require_admin
from database import get_db
from services import room_service
import schemas

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return room_service.list_active_rooms(db)


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    return room_service.create_room(db, body.name)
