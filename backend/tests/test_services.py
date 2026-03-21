# tests/test_services.py — unit tests for every service layer function
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

import models
from core.database import Base
from core.security import hash_password
from services import room_service
from infrastructure.websocket import ConnectionManager

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


@pytest.fixture()
def db():
    """Provide a fresh DB session and roll back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def room(db):
    r = models.Room(name="test_room")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def admin_user(db, room):
    u = models.User(username="admin_u", password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(models.RoomAdmin(user_id=u.id, room_id=room.id))
    db.commit()
    return u


@pytest.fixture()
def regular_user(db):
    u = models.User(username="regular_u", password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── is_admin_in_room ──────────────────────────────────────────────────────────

def test_is_admin_true(db, admin_user, room):
    assert room_service.is_admin_in_room(admin_user.username, room.id, db) is True


def test_is_admin_false_for_regular_user(db, regular_user, room):
    assert room_service.is_admin_in_room(regular_user.username, room.id, db) is False


def test_is_admin_false_for_nonexistent_user(db, room):
    assert room_service.is_admin_in_room("nobody", room.id, db) is False


# ── is_muted_in_room ──────────────────────────────────────────────────────────

def test_is_muted_false_initially(db, regular_user, room):
    assert room_service.is_muted_in_room(regular_user.username, room.id, db) is False


def test_is_muted_true_after_muting(db, admin_user, regular_user, room):
    room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    assert room_service.is_muted_in_room(regular_user.username, room.id, db) is True


def test_is_muted_false_for_nonexistent_user(db, room):
    assert room_service.is_muted_in_room("nobody", room.id, db) is False


# ── promote_to_admin ──────────────────────────────────────────────────────────

def test_promote_success(db, admin_user, regular_user, room):
    room_service.promote_to_admin(admin_user.username, regular_user.username, room.id, db)
    assert room_service.is_admin_in_room(regular_user.username, room.id, db) is True


def test_promote_self_raises_400(db, admin_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.promote_to_admin(admin_user.username, admin_user.username, room.id, db)
    assert exc.value.status_code == 400


def test_promote_by_non_admin_raises_403(db, regular_user, room):
    # Need a second user to be the target
    target = models.User(username="target_u", password_hash=hash_password("pw"))
    db.add(target)
    db.commit()
    db.refresh(target)
    with pytest.raises(HTTPException) as exc:
        room_service.promote_to_admin(regular_user.username, target.username, room.id, db)
    assert exc.value.status_code == 403


def test_promote_already_admin_raises_409(db, admin_user, room):
    second_admin = models.User(username="second_admin", password_hash=hash_password("pw"))
    db.add(second_admin)
    db.commit()
    db.refresh(second_admin)
    db.add(models.RoomAdmin(user_id=second_admin.id, room_id=room.id))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        room_service.promote_to_admin(admin_user.username, second_admin.username, room.id, db)
    assert exc.value.status_code == 409


def test_promote_muted_user_raises_403(db, admin_user, regular_user, room):
    """Old rule: muted users cannot become admin."""
    room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    with pytest.raises(HTTPException) as exc:
        room_service.promote_to_admin(admin_user.username, regular_user.username, room.id, db)
    assert exc.value.status_code == 403


def test_promote_nonexistent_user_raises_404(db, admin_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.promote_to_admin(admin_user.username, "ghost", room.id, db)
    assert exc.value.status_code == 404


# ── mute_user ─────────────────────────────────────────────────────────────────

def test_mute_success(db, admin_user, regular_user, room):
    room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    assert room_service.is_muted_in_room(regular_user.username, room.id, db) is True


def test_mute_self_raises_400(db, admin_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.mute_user(admin_user.username, admin_user.username, room.id, db)
    assert exc.value.status_code == 400


def test_mute_by_non_admin_raises_403(db, regular_user, room):
    other = models.User(username="other_u", password_hash=hash_password("pw"))
    db.add(other)
    db.commit()
    db.refresh(other)
    with pytest.raises(HTTPException) as exc:
        room_service.mute_user(regular_user.username, other.username, room.id, db)
    assert exc.value.status_code == 403


def test_mute_another_admin_raises_403(db, admin_user, room):
    second_admin = models.User(username="second_adm", password_hash=hash_password("pw"))
    db.add(second_admin)
    db.commit()
    db.refresh(second_admin)
    db.add(models.RoomAdmin(user_id=second_admin.id, room_id=room.id))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        room_service.mute_user(admin_user.username, second_admin.username, room.id, db)
    assert exc.value.status_code == 403


def test_mute_already_muted_raises_409(db, admin_user, regular_user, room):
    room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    with pytest.raises(HTTPException) as exc:
        room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    assert exc.value.status_code == 409


def test_mute_nonexistent_user_raises_404(db, admin_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.mute_user(admin_user.username, "ghost", room.id, db)
    assert exc.value.status_code == 404


# ── unmute_user ───────────────────────────────────────────────────────────────

def test_unmute_success(db, admin_user, regular_user, room):
    room_service.mute_user(admin_user.username, regular_user.username, room.id, db)
    room_service.unmute_user(admin_user.username, regular_user.username, room.id, db)
    assert room_service.is_muted_in_room(regular_user.username, room.id, db) is False


def test_unmute_by_non_admin_raises_403(db, regular_user, room):
    other = models.User(username="other2_u", password_hash=hash_password("pw"))
    db.add(other)
    db.commit()
    db.refresh(other)
    with pytest.raises(HTTPException) as exc:
        room_service.unmute_user(regular_user.username, other.username, room.id, db)
    assert exc.value.status_code == 403


def test_unmute_not_muted_raises_409(db, admin_user, regular_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.unmute_user(admin_user.username, regular_user.username, room.id, db)
    assert exc.value.status_code == 409


def test_unmute_nonexistent_user_raises_404(db, admin_user, room):
    with pytest.raises(HTTPException) as exc:
        room_service.unmute_user(admin_user.username, "ghost", room.id, db)
    assert exc.value.status_code == 404


# ── handle_admin_succession ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_succession_promotes_next_user(db, room):
    """Admin leaves → next user in join order is promoted."""
    admin = models.User(username="succ_admin", password_hash=hash_password("pw"))
    next_u = models.User(username="succ_next", password_hash=hash_password("pw"))
    db.add_all([admin, next_u])
    db.commit()
    db.refresh(admin)
    db.refresh(next_u)
    db.add(models.RoomAdmin(user_id=admin.id, room_id=room.id))
    db.commit()

    mgr = ConnectionManager()
    # Simulate join order: admin joined first, next_u joined second
    mgr.room_join_order[room.id] = [next_u.username]  # after admin leaves, next_u is first

    await room_service.handle_admin_succession(room.id, admin.username, db, mgr)

    assert room_service.is_admin_in_room(admin.username, room.id, db) is False
    assert room_service.is_admin_in_room(next_u.username, room.id, db) is True


@pytest.mark.asyncio
async def test_admin_succession_no_successor_does_nothing(db, room):
    """Admin leaves empty room → no error, no successor."""
    admin = models.User(username="lonely_admin", password_hash=hash_password("pw"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    db.add(models.RoomAdmin(user_id=admin.id, room_id=room.id))
    db.commit()

    mgr = ConnectionManager()
    mgr.room_join_order[room.id] = []  # no one else in room

    await room_service.handle_admin_succession(room.id, admin.username, db, mgr)
    assert room_service.is_admin_in_room(admin.username, room.id, db) is False


# ── handle_admin_succession clears all mutes ──────────────────────────────────

@pytest.mark.asyncio
async def test_admin_succession_clears_all_mutes(db, room):
    """When admin leaves, all mutes in the room should be cleared."""
    admin = models.User(username="mute_succ_admin", password_hash=hash_password("pw"))
    victim1 = models.User(username="mute_succ_v1", password_hash=hash_password("pw"))
    victim2 = models.User(username="mute_succ_v2", password_hash=hash_password("pw"))
    db.add_all([admin, victim1, victim2])
    db.commit()
    for u in [admin, victim1, victim2]:
        db.refresh(u)

    db.add(models.RoomAdmin(user_id=admin.id, room_id=room.id))
    db.add(models.MutedUser(user_id=victim1.id, room_id=room.id))
    db.add(models.MutedUser(user_id=victim2.id, room_id=room.id))
    db.commit()

    mgr = ConnectionManager()
    mgr.room_join_order[room.id] = []  # admin is last user, no successor

    await room_service.handle_admin_succession(room.id, admin.username, db, mgr)

    # Both mutes should be gone
    mutes = db.query(models.MutedUser).filter(models.MutedUser.room_id == room.id).all()
    assert len(mutes) == 0
