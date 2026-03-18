# routers/rooms.py — Controller for room listing, creation, and user queries
import hashlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from typing import List

from auth import get_current_user, require_admin
from database import get_db
from services import room_service
from ws_manager import manager as ws_manager
import schemas

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def broadcast_room_list(db: Session) -> None:
    """Push the current room list to all connected lobby sockets."""
    rooms = room_service.list_active_rooms(db)
    data = [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]
    await ws_manager.broadcast_all({"type": "room_list_updated", "rooms": data})


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rooms = room_service.list_active_rooms(db)
    return [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
async def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    room = room_service.create_room(db, body.name)
    await broadcast_room_list(db)
    return room


@router.get("/{room_id}/users")
def get_room_users(
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    room_service.get_room_or_404(db, room_id)
    users = ws_manager.get_users_in_room(room_id)
    etag = f'"{hashlib.md5(",".join(sorted(users)).encode()).hexdigest()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse({"users": users}, headers={"ETag": etag})
