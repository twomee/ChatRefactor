# tests/test_admin.py — comprehensive admin route tests
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from main import app
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=test_engine)
with TestSessionLocal() as _db:
    for _name in ["politics", "sports", "movies"]:
        if not _db.query(models.Room).filter(models.Room.name == _name).first():
            _db.add(models.Room(name=_name))
    if not _db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
        _db.add(models.User(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), is_global_admin=True))
    _db.commit()

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


def _admin_token():
    resp = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    return resp.json()["access_token"]


def _user_token(username="regular_user", password="pw"):
    client.post("/auth/register", json={"username": username, "password": password})
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


# ── Access control ─────────────────────────────────────────────────────────────

def test_admin_endpoints_require_admin_token():
    token = _user_token("nonadmin1")
    for method, url in [
        ("GET", "/admin/users"),
        ("GET", "/admin/rooms"),
        ("POST", "/admin/chat/close"),
        ("POST", "/admin/chat/open"),
        ("DELETE", "/admin/db"),
    ]:
        resp = client.request(method, url, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"{method} {url} should return 403 for non-admin"


def test_admin_endpoints_reject_no_token():
    for method, url in [("GET", "/admin/users"), ("GET", "/admin/rooms")]:
        resp = client.request(method, url)
        assert resp.status_code == 401


# ── GET /admin/users ──────────────────────────────────────────────────────────

def test_get_connected_users_returns_dict():
    token = _admin_token()
    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ── GET /admin/rooms ──────────────────────────────────────────────────────────

def test_get_rooms_returns_list_with_seeded_rooms():
    token = _admin_token()
    resp = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "politics" in names
    assert "sports" in names
    assert "movies" in names


def test_get_rooms_includes_is_active_field():
    token = _admin_token()
    rooms = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    assert all("is_active" in r for r in rooms)


# ── POST /admin/chat/close and /admin/chat/open ───────────────────────────────

def test_close_all_rooms_sets_is_active_false():
    token = _admin_token()
    client.post("/admin/chat/close", headers={"Authorization": f"Bearer {token}"})
    rooms = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    assert all(not r["is_active"] for r in rooms)


def test_open_all_rooms_sets_is_active_true():
    token = _admin_token()
    client.post("/admin/chat/close", headers={"Authorization": f"Bearer {token}"})
    client.post("/admin/chat/open", headers={"Authorization": f"Bearer {token}"})
    rooms = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    assert all(r["is_active"] for r in rooms)


# ── POST /admin/rooms/{id}/close and /admin/rooms/{id}/open ──────────────────

def test_close_specific_room_only_affects_that_room():
    token = _admin_token()
    # First ensure all open
    client.post("/admin/chat/open", headers={"Authorization": f"Bearer {token}"})
    rooms = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    target_id = rooms[0]["id"]
    other_ids = [r["id"] for r in rooms[1:]]

    resp = client.post(f"/admin/rooms/{target_id}/close", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    rooms_after = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    by_id = {r["id"]: r for r in rooms_after}
    assert by_id[target_id]["is_active"] is False
    for oid in other_ids:
        assert by_id[oid]["is_active"] is True


def test_open_specific_room_only_affects_that_room():
    token = _admin_token()
    client.post("/admin/chat/close", headers={"Authorization": f"Bearer {token}"})
    rooms = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    target_id = rooms[0]["id"]

    resp = client.post(f"/admin/rooms/{target_id}/open", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    rooms_after = client.get("/admin/rooms", headers={"Authorization": f"Bearer {token}"}).json()
    by_id = {r["id"]: r for r in rooms_after}
    assert by_id[target_id]["is_active"] is True


def test_close_nonexistent_room_returns_404():
    token = _admin_token()
    resp = client.post("/admin/rooms/99999/close", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_open_nonexistent_room_returns_404():
    token = _admin_token()
    resp = client.post("/admin/rooms/99999/open", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ── DELETE /admin/db ──────────────────────────────────────────────────────────

def test_reset_db_removes_regular_users():
    token = _admin_token()
    _user_token("todelete1")
    _user_token("todelete2")
    client.delete("/admin/db", headers={"Authorization": f"Bearer {token}"})
    # Regular users should not be able to login anymore
    resp = client.post("/auth/login", json={"username": "todelete1", "password": "pw"})
    assert resp.status_code == 401


def test_reset_db_restores_admin_user():
    token = _admin_token()
    client.delete("/admin/db", headers={"Authorization": f"Bearer {token}"})
    # Admin should still be able to login
    resp = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["is_global_admin"] is True


# ── POST /admin/promote ───────────────────────────────────────────────────────

def test_promote_user_in_all_rooms():
    token = _admin_token()
    client.post("/auth/register", json={"username": "promoteme", "password": "pw"})
    resp = client.post("/admin/promote?username=promoteme", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "promoted" in resp.json()["message"].lower()


def test_promote_nonexistent_user_returns_404():
    token = _admin_token()
    resp = client.post("/admin/promote?username=nobody_exists", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ── POST /rooms/ ──────────────────────────────────────────────────────────────

def test_admin_can_create_room():
    token = _admin_token()
    resp = client.post("/rooms/", json={"name": "new_test_room"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "new_test_room"


def test_admin_create_duplicate_room_returns_409():
    token = _admin_token()
    client.post("/rooms/", json={"name": "dup_room"}, headers={"Authorization": f"Bearer {token}"})
    resp = client.post("/rooms/", json={"name": "dup_room"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409


def test_non_admin_cannot_create_room():
    token = _user_token("nonadmin_create")
    resp = client.post("/rooms/", json={"name": "no_perm_room"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
