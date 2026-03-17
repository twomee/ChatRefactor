# routers/admin.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import require_admin
from ws_manager import manager
import models
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def get_connected_users(_=Depends(require_admin)):
    """Old: tornadoWeb UsersHandler — polled every 5 seconds. Now: on-demand."""
    all_users = {}
    for room_id, sockets in manager.rooms.items():
        all_users[room_id] = manager.get_users_in_room(room_id)
    return all_users


@router.get("/rooms")
def get_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(models.Room).all()


@router.post("/chat/close")
async def close_chat(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb BlockHandler — kick all users and block new connections."""
    for room in db.query(models.Room).all():
        room.is_active = False
        # Kick all connected users from this room
        await manager.broadcast(room.id, {"type": "chat_closed", "detail": "Admin has closed the chat"})
    db.commit()
    # Close all active WebSocket connections
    for room_id, sockets in list(manager.rooms.items()):
        for ws in list(sockets):
            await ws.close()
    return {"message": "Chat closed"}


@router.post("/chat/open")
def open_chat(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb OpenHandler."""
    for room in db.query(models.Room).all():
        room.is_active = True
    db.commit()
    return {"message": "Chat opened"}


@router.delete("/db")
def reset_database(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb DatabaseHandler — wipe users so they must re-register.
    Admin user is recreated immediately after the wipe."""
    db.query(models.RoomAdmin).delete()
    db.query(models.MutedUser).delete()
    db.query(models.User).delete()
    db.commit()
    # Re-create admin user
    db.add(models.User(
        username=ADMIN_USERNAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        is_global_admin=True,
    ))
    db.commit()
    return {"message": "Database reset. Admin user restored."}


@router.post("/promote")
def promote_user(username: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb addAdminHandler — promote user to admin in ALL rooms."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return {"error": "User not found"}
    for room in db.query(models.Room).all():
        exists = db.query(models.RoomAdmin).filter(
            models.RoomAdmin.user_id == user.id,
            models.RoomAdmin.room_id == room.id,
        ).first()
        if not exists:
            db.add(models.RoomAdmin(user_id=user.id, room_id=room.id))
    db.commit()
    return {"message": f"{username} promoted to admin in all rooms"}
