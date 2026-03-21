# services/room_service.py — Business logic for room operations (admin, mute, promote)
from fastapi import HTTPException
from sqlalchemy.orm import Session

from dal import room_dal, user_dal
from infrastructure.websocket import ConnectionManager
from infrastructure.websocket import manager as _ws_manager


def _require_user(db: Session, username: str):
    """Lookup user by username; raise 404 if not found."""
    user = user_dal.get_by_username(db, username)
    if not user:
        raise HTTPException(404, "Target user not found")
    return user


# ── Query helpers ─────────────────────────────────────────────────────


def is_admin_in_room(username: str, room_id: int, db: Session) -> bool:
    user = user_dal.get_by_username(db, username)
    if not user:
        return False
    return room_dal.is_admin(db, user.id, room_id)


def is_muted_in_room(username: str, room_id: int, db: Session) -> bool:
    user = user_dal.get_by_username(db, username)
    if not user:
        return False
    return room_dal.is_muted(db, user.id, room_id)


def get_admins_in_room(room_id: int, db: Session, users_in_room: list[str]) -> list[str]:
    """Filter connected users to those who are admins in this room."""
    return [u for u in users_in_room if is_admin_in_room(u, room_id, db)]


def get_muted_in_room(room_id: int, db: Session, users_in_room: list[str]) -> list[str]:
    """Filter connected users to those who are muted in this room."""
    return [u for u in users_in_room if is_muted_in_room(u, room_id, db)]


# ── Broadcast helpers ─────────────────────────────────────────────────


async def broadcast_room_list(db: Session) -> None:
    """Push the current room list to all connected lobby sockets."""
    rooms = list_active_rooms(db)
    data = [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]
    await _ws_manager.broadcast_all({"type": "room_list_updated", "rooms": data})


# ── Room CRUD (used by rooms router) ─────────────────────────────────


def list_active_rooms(db: Session):
    return room_dal.list_active(db)


def create_room(db: Session, name: str):
    if room_dal.get_by_name(db, name):
        raise HTTPException(status_code=409, detail="Room name already exists")
    return room_dal.create(db, name.strip())


def get_room_or_404(db: Session, room_id: int):
    room = room_dal.get_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


# ── Admin actions ─────────────────────────────────────────────────────


def promote_to_admin(actor: str, target: str, room_id: int, db: Session):
    if actor == target:
        raise HTTPException(400, "Cannot promote yourself")
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can promote users")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(409, "User is already an admin")
    if is_muted_in_room(target, room_id, db):
        raise HTTPException(403, "Cannot promote a muted user — unmute first")
    target_user = _require_user(db, target)
    room_dal.add_admin(db, target_user.id, room_id)


def mute_user(actor: str, target: str, room_id: int, db: Session):
    if actor == target:
        raise HTTPException(400, "Cannot mute yourself")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(403, "Cannot mute another admin")
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can mute users")
    if is_muted_in_room(target, room_id, db):
        raise HTTPException(409, "User is already muted")
    target_user = _require_user(db, target)
    room_dal.add_mute(db, target_user.id, room_id)


def unmute_user(actor: str, target: str, room_id: int, db: Session):
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can unmute users")
    target_user = _require_user(db, target)
    if not room_dal.is_muted(db, target_user.id, room_id):
        raise HTTPException(409, "User is not muted")
    room_dal.remove_mute(db, target_user.id, room_id)


# ── Connection lifecycle helpers ──────────────────────────────────────


def auto_promote_first_user(user, room_id: int, db: Session) -> bool:
    """Make the first user in a room the admin automatically. Returns True if promoted."""
    if not is_admin_in_room(user.username, room_id, db):
        room_dal.add_admin(db, user.id, room_id)
        return True
    return False


def clear_user_mute_on_leave(user, room_id: int, db: Session) -> bool:
    """Clear mute for a user leaving a room. Returns True if was muted."""
    if room_dal.is_muted(db, user.id, room_id):
        room_dal.remove_mute(db, user.id, room_id)
        return True
    return False


def force_clear_mute(user_id: int, room_id: int, db: Session):
    """Force-clear mute record (used during kick disconnect)."""
    room_dal.remove_mute(db, user_id, room_id)


async def handle_admin_succession(room_id: int, leaving_username: str, db: Session, mgr: ConnectionManager):
    """When an admin leaves, remove their admin status, clear all mutes (amnesty),
    and promote the next user in join order."""
    leaving_user = user_dal.get_by_username(db, leaving_username)
    if leaving_user:
        room_dal.remove_admin(db, leaving_user.id, room_id)

    unmuted_usernames = room_dal.clear_room_mutes(db, room_id)
    for username in unmuted_usernames:
        await mgr.broadcast(room_id, {"type": "unmuted", "username": username, "room_id": room_id})

    successor = mgr.get_admin_successor(room_id)
    if successor:
        successor_user = user_dal.get_by_username(db, successor)
        if successor_user and not room_dal.is_admin(db, successor_user.id, room_id):
            room_dal.add_admin(db, successor_user.id, room_id)
            await mgr.broadcast(room_id, {"type": "new_admin", "username": successor, "room_id": room_id})
            await mgr.broadcast(
                room_id,
                {
                    "type": "system",
                    "text": f"{successor} has become admin",
                    "room_id": room_id,
                },
            )
