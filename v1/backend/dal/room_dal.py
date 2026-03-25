# dal/room_dal.py — Data Access Layer for Room, RoomAdmin, and MutedUser models
from sqlalchemy.orm import Session

import models

# ── Room ──────────────────────────────────────────────────────────────


def get_by_id(db: Session, room_id: int) -> models.Room | None:
    return db.query(models.Room).filter(models.Room.id == room_id).first()


def get_by_name(db: Session, name: str) -> models.Room | None:
    return db.query(models.Room).filter(models.Room.name == name).first()


def list_active(db: Session) -> list[models.Room]:
    return db.query(models.Room).filter(models.Room.is_active == True).all()


def list_all(db: Session) -> list[models.Room]:
    return db.query(models.Room).all()


def create(db: Session, name: str) -> models.Room:
    room = models.Room(name=name)
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def set_active(db: Session, room: models.Room, is_active: bool):
    room.is_active = is_active
    db.commit()


def set_all_active(db: Session, is_active: bool) -> list[models.Room]:
    rooms = list_all(db)
    for room in rooms:
        room.is_active = is_active
    db.commit()
    return rooms


# ── RoomAdmin ─────────────────────────────────────────────────────────


def is_admin(db: Session, user_id: int, room_id: int) -> bool:
    return (
        db.query(models.RoomAdmin)
        .filter(
            models.RoomAdmin.user_id == user_id,
            models.RoomAdmin.room_id == room_id,
        )
        .first()
        is not None
    )


def add_admin(db: Session, user_id: int, room_id: int):
    db.add(models.RoomAdmin(user_id=user_id, room_id=room_id))
    db.commit()


def remove_admin(db: Session, user_id: int, room_id: int):
    db.query(models.RoomAdmin).filter(
        models.RoomAdmin.user_id == user_id,
        models.RoomAdmin.room_id == room_id,
    ).delete()
    db.commit()


def remove_all_admins(db: Session):
    db.query(models.RoomAdmin).delete()
    db.commit()


# ── MutedUser ─────────────────────────────────────────────────────────


def is_muted(db: Session, user_id: int, room_id: int) -> bool:
    return (
        db.query(models.MutedUser)
        .filter(
            models.MutedUser.user_id == user_id,
            models.MutedUser.room_id == room_id,
        )
        .first()
        is not None
    )


def add_mute(db: Session, user_id: int, room_id: int):
    db.add(models.MutedUser(user_id=user_id, room_id=room_id))
    db.commit()


def remove_mute(db: Session, user_id: int, room_id: int):
    db.query(models.MutedUser).filter(
        models.MutedUser.user_id == user_id,
        models.MutedUser.room_id == room_id,
    ).delete()
    db.commit()


def clear_room_mutes(db: Session, room_id: int) -> list[str]:
    """Clear all mutes in a room. Returns list of unmuted usernames."""
    mutes = (
        db.query(models.MutedUser, models.User)
        .join(models.User, models.MutedUser.user_id == models.User.id)
        .filter(models.MutedUser.room_id == room_id)
        .all()
    )
    usernames = [u.username for _, u in mutes]
    db.query(models.MutedUser).filter(models.MutedUser.room_id == room_id).delete()
    db.commit()
    return usernames


def remove_all_mutes(db: Session):
    db.query(models.MutedUser).delete()
    db.commit()
