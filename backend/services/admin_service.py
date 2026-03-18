# services/admin_service.py — Business logic for admin operations
from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from dal import user_dal, room_dal, message_dal
from ws_manager import ConnectionManager


def get_connected_users(mgr: ConnectionManager) -> dict:
    return {room_id: mgr.get_users_in_room(room_id) for room_id in mgr.rooms}


def get_all_rooms(db: Session):
    return room_dal.list_all(db)


async def close_all_rooms(db: Session, mgr: ConnectionManager):
    rooms = room_dal.set_all_active(db, False)
    for room in rooms:
        await mgr.broadcast(room.id, {"type": "chat_closed", "detail": "Admin has closed the chat"})
    for room_id, sockets in list(mgr.rooms.items()):
        for ws in list(sockets):
            try:
                await ws.close()
            except Exception:
                pass
    return {"message": "All rooms closed"}


def open_all_rooms(db: Session):
    room_dal.set_all_active(db, True)
    return {"message": "All rooms opened"}


async def close_room(db: Session, room_id: int, mgr: ConnectionManager):
    room = room_dal.get_by_id(db, room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    room_dal.set_active(db, room, False)
    await mgr.broadcast(room_id, {
        "type": "chat_closed",
        "detail": f"Room '{room.name}' has been closed by admin",
    })
    for ws in list(mgr.rooms.get(room_id, [])):
        try:
            await ws.close()
        except Exception:
            pass
    return {"message": f"Room '{room.name}' closed"}


def open_room(db: Session, room_id: int):
    room = room_dal.get_by_id(db, room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    room_dal.set_active(db, room, True)
    return {"message": f"Room '{room.name}' opened"}


def reset_database(db: Session):
    room_dal.remove_all_admins(db)
    room_dal.remove_all_mutes(db)
    message_dal.delete_all(db)
    user_dal.delete_all(db)
    user_dal.create(db, username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), is_global_admin=True)
    return {"message": "Database reset. Admin user restored."}


def promote_user_global(db: Session, username: str):
    user = user_dal.get_by_username(db, username)
    if not user:
        raise HTTPException(404, "User not found")
    rooms = room_dal.list_all(db)
    for room in rooms:
        if not room_dal.is_admin(db, user.id, room.id):
            room_dal.add_admin(db, user.id, room.id)
    return {"message": f"{username} promoted to admin in all rooms"}
