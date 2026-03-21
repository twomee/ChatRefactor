# services/admin_service.py — Business logic for admin operations
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.security import hash_password
from core.config import ADMIN_USERNAME, ADMIN_PASSWORD, APP_ENV
from dal import user_dal, room_dal, message_dal
from core.logging import get_logger
from infrastructure.websocket import ConnectionManager

logger = get_logger("services.admin")


def get_connected_users(mgr: ConnectionManager) -> dict:
    per_room = {room_id: mgr.get_users_in_room(room_id) for room_id in mgr.rooms}
    all_online = list(mgr.logged_in_users)
    return {"all_online": all_online, "per_room": per_room}


def get_all_rooms(db: Session):
    return room_dal.list_all(db)


async def close_all_rooms(db: Session, mgr: ConnectionManager):
    rooms = room_dal.set_all_active(db, False)
    logger.info("all_rooms_closed", count=len(rooms))
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
    logger.info("all_rooms_opened")
    return {"message": "All rooms opened"}


async def close_room(db: Session, room_id: int, mgr: ConnectionManager):
    room = room_dal.get_by_id(db, room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    room_dal.set_active(db, room, False)
    logger.info("room_closed", room_id=room_id, room_name=room.name)
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
    logger.info("room_opened", room_id=room_id, room_name=room.name)
    return {"message": f"Room '{room.name}' opened"}


def reset_database(db: Session):
    # SECURITY: Only allow database reset in dev/staging — never in production
    if APP_ENV == "prod":
        logger.error("database_reset_blocked", reason="Attempted in production environment")
        raise HTTPException(403, "Database reset is disabled in production")

    logger.warning("database_reset_triggered", env=APP_ENV)
    room_dal.remove_all_admins(db)
    room_dal.remove_all_mutes(db)
    message_dal.delete_all(db)
    user_dal.delete_all(db)
    user_dal.create(db, username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), is_global_admin=True)
    return {"message": "Database reset. Admin user restored."}


async def promote_user_in_connected_rooms(db: Session, username: str, mgr: ConnectionManager):
    """Promote a user to admin only in rooms they currently have an active WebSocket in."""
    user = user_dal.get_by_username(db, username)
    if not user:
        raise HTTPException(404, "User not found")

    rooms_promoted = []
    for room_id in list(mgr.rooms.keys()):
        if mgr.is_user_in_room(username, room_id):
            if not room_dal.is_admin(db, user.id, room_id):
                room_dal.add_admin(db, user.id, room_id)
                rooms_promoted.append(room_id)

    for room_id in rooms_promoted:
        await mgr.broadcast(room_id, {"type": "new_admin", "username": username, "room_id": room_id})
        await mgr.broadcast(room_id, {
            "type": "system",
            "text": f"{username} has been promoted to admin by the global admin",
            "room_id": room_id,
        })

    if rooms_promoted:
        logger.info("user_promoted_globally", username=username, rooms=rooms_promoted)

    if not rooms_promoted:
        return {"message": f"{username} is not currently connected to any rooms"}
    return {"message": f"{username} promoted to admin in {len(rooms_promoted)} room(s)"}
