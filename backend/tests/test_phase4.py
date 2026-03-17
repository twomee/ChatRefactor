# tests/test_phase4.py
import sys
import os
import io
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

# Isolated in-memory DB for Phase 4 tests
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

Base.metadata.create_all(bind=test_engine)
with TestSessionLocal() as _db:
    for _name in ["politics", "sports", "movies"]:
        if not _db.query(models.Room).filter(models.Room.name == _name).first():
            _db.add(models.Room(name=_name))
    if not _db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
        _db.add(models.User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_global_admin=True,
        ))
    _db.commit()

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


def _login(username: str, password: str) -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _register_and_login(username: str, password: str = "pass123") -> str:
    client.post("/auth/register", json={"username": username, "password": password})
    return _login(username, password)


def test_file_upload():
    """POST /files/upload returns 200 and FileResponse with file metadata."""
    token = _register_and_login("uploader")
    file_content = b"Hello, this is a test file!"
    resp = client.post(
        "/files/upload?room_id=1",
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_name"] == "test.txt"
    assert data["file_size"] == len(file_content)
    assert data["room_id"] == 1


def test_file_download():
    """GET /files/download/{id} returns the file bytes with original filename."""
    token = _register_and_login("downloader")
    file_content = b"Downloadable content"

    # Upload first
    upload_resp = client.post(
        "/files/upload?room_id=1",
        files={"file": ("download_me.txt", io.BytesIO(file_content), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_resp.status_code == 200
    file_id = upload_resp.json()["id"]

    # Now download
    dl_resp = client.get(
        f"/files/download/{file_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.content == file_content


def test_admin_route_requires_admin_token():
    """GET /admin/users without admin token returns 403."""
    regular_token = _register_and_login("regular_user4")
    resp = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert resp.status_code == 403

    # Admin token should work
    admin_token = _login(ADMIN_USERNAME, ADMIN_PASSWORD)
    admin_resp = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_resp.status_code == 200
