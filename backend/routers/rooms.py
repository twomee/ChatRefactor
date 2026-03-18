# routers/rooms.py — Controller for room listing, creation, and user queries
# Note: ETag caching is an HTTP-level concern and stays in the router layer.
import hashlib
import time

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

# ── In-memory cache for GET /rooms/ ──────────────────────────────────
_rooms_cache: dict = {"data": None, "etag": None, "ts": 0.0}
CACHE_TTL = 1.0  # seconds


def invalidate_rooms_cache() -> None:
    """Call this whenever a room is created, closed, or reopened."""
    _rooms_cache["ts"] = 0.0


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    now = time.time()
    if _rooms_cache["data"] is None or now - _rooms_cache["ts"] > CACHE_TTL:
        rooms = room_service.list_active_rooms(db)
        data = [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]
        etag = f'"{hashlib.md5(str(data).encode()).hexdigest()}"'
        _rooms_cache.update({"data": data, "etag": etag, "ts": now})

    etag = _rooms_cache["etag"]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse(_rooms_cache["data"], headers={"ETag": etag})


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    room = room_service.create_room(db, body.name)
    invalidate_rooms_cache()
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
