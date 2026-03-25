# routers/rooms.py — Controller for room listing, creation, and user queries
import hashlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

import schemas
from core.database import get_db
from core.security import get_current_user, require_admin
from infrastructure.websocket import manager as ws_manager
from services import room_service

router = APIRouter(prefix="/rooms", tags=["rooms"])


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/", response_model=list[schemas.RoomResponse])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rooms = room_service.list_active_rooms(db)
    return [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
async def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    room = room_service.create_room(db, body.name)
    await room_service.broadcast_room_list(db)
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
    etag = f'"{hashlib.sha256(",".join(sorted(users)).encode()).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse({"users": users}, headers={"ETag": etag})
