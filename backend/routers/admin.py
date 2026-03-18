# routers/admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import require_admin
from ws_manager import manager
import models
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from routers.rooms import invalidate_rooms_cache

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def get_connected_users(_=Depends(require_admin)):
    """Return currently connected users per room."""
    all_users = {}
    for room_id in manager.rooms:
        all_users[room_id] = manager.get_users_in_room(room_id)
    return all_users


@router.get("/rooms")
def get_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(models.Room).all()


@router.post("/chat/close")
async def close_all_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Close ALL rooms — kick all users and block new connections."""
    for room in db.query(models.Room).all():
        room.is_active = False
        await manager.broadcast(room.id, {"type": "chat_closed", "detail": "Admin has closed the chat"})
    db.commit()
    invalidate_rooms_cache()
    for room_id, sockets in list(manager.rooms.items()):
        for ws in list(sockets):
            try:
                await ws.close()
            except Exception:
                pass
    return {"message": "All rooms closed"}


@router.post("/chat/open")
def open_all_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Open ALL rooms."""
    for room in db.query(models.Room).all():
        room.is_active = True
    db.commit()
    invalidate_rooms_cache()
    return {"message": "All rooms opened"}


@router.post("/rooms/{room_id}/close")
async def close_room(room_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Close a specific room — kick its users and block new connections."""
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    room.is_active = False
    db.commit()
    invalidate_rooms_cache()
    await manager.broadcast(room_id, {"type": "chat_closed", "detail": f"Room '{room.name}' has been closed by admin"})
    for ws in list(manager.rooms.get(room_id, [])):
        try:
            await ws.close()
        except Exception:
            pass
    return {"message": f"Room '{room.name}' closed"}


@router.post("/rooms/{room_id}/open")
def open_room(room_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Reopen a specific room."""
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    room.is_active = True
    db.commit()
    invalidate_rooms_cache()
    return {"message": f"Room '{room.name}' opened"}


@router.delete("/db")
def reset_database(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Wipe all users/admins/mutes. Admin user is recreated immediately."""
    db.query(models.RoomAdmin).delete()
    db.query(models.MutedUser).delete()
    db.query(models.Message).delete()
    db.query(models.User).delete()
    db.commit()
    db.add(models.User(
        username=ADMIN_USERNAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        is_global_admin=True,
    ))
    db.commit()
    return {"message": "Database reset. Admin user restored."}


@router.post("/promote")
def promote_user(username: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Promote a user to admin in ALL rooms."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    for room in db.query(models.Room).all():
        exists = db.query(models.RoomAdmin).filter(
            models.RoomAdmin.user_id == user.id,
            models.RoomAdmin.room_id == room.id,
        ).first()
        if not exists:
            db.add(models.RoomAdmin(user_id=user.id, room_id=room.id))
    db.commit()
    return {"message": f"{username} promoted to admin in all rooms"}
