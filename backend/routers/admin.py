# routers/admin.py — Thin controller for admin operations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from routers.rooms import broadcast_room_list
from services import admin_service
from ws_manager import manager

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def get_connected_users(_=Depends(require_admin)):
    return admin_service.get_connected_users(manager)


@router.get("/rooms")
def get_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    return admin_service.get_all_rooms(db)


@router.post("/chat/close")
async def close_all_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    result = await admin_service.close_all_rooms(db, manager)
    await broadcast_room_list(db)
    return result


@router.post("/chat/open")
async def open_all_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    result = admin_service.open_all_rooms(db)
    await broadcast_room_list(db)
    return result


@router.post("/rooms/{room_id}/close")
async def close_room(room_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    result = await admin_service.close_room(db, room_id, manager)
    await broadcast_room_list(db)
    return result


@router.post("/rooms/{room_id}/open")
async def open_room(room_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    result = admin_service.open_room(db, room_id)
    await broadcast_room_list(db)
    return result


@router.delete("/db")
async def reset_database(db: Session = Depends(get_db), _=Depends(require_admin)):
    result = admin_service.reset_database(db)
    await broadcast_room_list(db)
    return result


@router.post("/promote")
async def promote_user(username: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    return await admin_service.promote_user_in_connected_rooms(db, username, manager)
