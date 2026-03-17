# services/room_service.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
import models
from ws_manager import ConnectionManager


def is_admin_in_room(username: str, room_id: int, db: Session) -> bool:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return False
    return db.query(models.RoomAdmin).filter(
        models.RoomAdmin.user_id == user.id,
        models.RoomAdmin.room_id == room_id,
    ).first() is not None


def is_muted_in_room(username: str, room_id: int, db: Session) -> bool:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return False
    return db.query(models.MutedUser).filter(
        models.MutedUser.user_id == user.id,
        models.MutedUser.room_id == room_id,
    ).first() is not None


def promote_to_admin(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminAppendToAdmins() — admin adds user to admin text file."""
    if actor == target:
        raise HTTPException(400, "Cannot promote yourself")
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can promote users")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(409, "User is already an admin")  # old: server sent error message to client

    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    db.add(models.RoomAdmin(user_id=target_user.id, room_id=room_id))
    db.commit()


def mute_user(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminMute() — added to _usersToMute list (lost on restart)."""
    if actor == target:
        raise HTTPException(400, "Cannot mute yourself")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(403, "Cannot mute another admin")  # old: security rule
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can mute users")
    if is_muted_in_room(target, room_id, db):
        raise HTTPException(409, "User is already muted")

    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    db.add(models.MutedUser(user_id=target_user.id, room_id=room_id))
    db.commit()


def unmute_user(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminUnMute()."""
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can unmute users")
    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    mute = db.query(models.MutedUser).filter(
        models.MutedUser.user_id == target_user.id,
        models.MutedUser.room_id == room_id,
    ).first()
    if not mute:
        raise HTTPException(409, "User is not muted")  # old: server sent error to client
    db.delete(mute)
    db.commit()


async def handle_admin_succession(room_id: int, leaving_username: str, db: Session, manager: ConnectionManager):
    """
    Old: chatServer logic — when admin leaves, next user in join order becomes admin.
    'כאשר מנהל יוצא מן החדר, המשתמש שנכנס אחרי המנהל הוא זה שיהפוך למנהל'
    """
    # Remove admin status for the leaving user
    leaving_user = db.query(models.User).filter(models.User.username == leaving_username).first()
    if leaving_user:
        db.query(models.RoomAdmin).filter(
            models.RoomAdmin.user_id == leaving_user.id,
            models.RoomAdmin.room_id == room_id,
        ).delete()
        db.commit()

    # Promote the next user in join order
    successor = manager.get_admin_successor(room_id)
    if successor:
        successor_user = db.query(models.User).filter(models.User.username == successor).first()
        if successor_user and not is_admin_in_room(successor, room_id, db):
            db.add(models.RoomAdmin(user_id=successor_user.id, room_id=room_id))
            db.commit()
            await manager.broadcast(room_id, {
                "type": "new_admin",
                "username": successor,
                "room_id": room_id,
            })
