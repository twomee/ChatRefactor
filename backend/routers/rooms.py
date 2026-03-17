# routers/rooms.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from auth import get_current_user, require_admin
import models, schemas

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.Room).filter(models.Room.is_active == True).all()


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    # Old code: tornadoWeb addRoomHandler — only global admin could add rooms
    if db.query(models.Room).filter(models.Room.name == body.name).first():
        raise HTTPException(status_code=409, detail="Room name already exists")
    room = models.Room(name=body.name.strip())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room
