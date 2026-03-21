# tests/test_files.py — comprehensive file upload/download/list tests
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
from core.database import Base, get_db
from main import app
from core.security import hash_password
from core.config import ADMIN_USERNAME, ADMIN_PASSWORD

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


def _token(username="file_user", password="password123"):
    client.post("/auth/register", json={"username": username, "password": password})
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _room_id():
    with TestSessionLocal() as db:
        room = db.query(models.Room).filter(models.Room.name == "politics").first()
        return room.id


# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_file_returns_200_and_metadata():
    token = _token("uploader1")
    content = b"hello world content"
    resp = client.post(
        f"/files/upload?room_id={_room_id()}",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_name"] == "test.txt"
    assert data["file_size"] == len(content)
    assert data["sender"] == "uploader1"


def test_upload_file_without_token_returns_401():
    resp = client.post(
        f"/files/upload?room_id={_room_id()}",
        files={"file": ("t.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 401


def test_upload_multiple_files_increments_list():
    token = _token("uploader2")
    rid = _room_id()
    for i in range(3):
        client.post(
            f"/files/upload?room_id={rid}",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"file{i}.txt", io.BytesIO(b"data"), "text/plain")},
        )
    resp = client.get(f"/files/room/{rid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


def test_upload_file_exceeding_150mb_returns_413():
    token = _token("uploader3")
    big = io.BytesIO(b"x" * (151 * 1024 * 1024))  # 151 MB
    resp = client.post(
        f"/files/upload?room_id={_room_id()}",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.bin", big, "application/octet-stream")},
    )
    assert resp.status_code == 413


# ── Download ──────────────────────────────────────────────────────────────────

def test_download_returns_exact_bytes():
    token = _token("downloader1")
    content = b"download me exactly"
    upload_resp = client.post(
        f"/files/upload?room_id={_room_id()}",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("dl.bin", io.BytesIO(content), "application/octet-stream")},
    )
    file_id = upload_resp.json()["id"]
    dl_resp = client.get(f"/files/download/{file_id}", headers={"Authorization": f"Bearer {token}"})
    assert dl_resp.status_code == 200
    assert dl_resp.content == content


def test_download_nonexistent_file_returns_404():
    token = _token("downloader2")
    resp = client.get("/files/download/999999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_download_without_token_returns_401():
    resp = client.get("/files/download/1")
    assert resp.status_code == 401


# ── List room files ───────────────────────────────────────────────────────────

def test_list_room_files_returns_list():
    token = _token("lister1")
    rid = _room_id()
    resp = client.get(f"/files/room/{rid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_room_files_without_token_returns_401():
    resp = client.get(f"/files/room/{_room_id()}")
    assert resp.status_code == 401


def test_list_room_files_includes_uploaded_files():
    token = _token("lister2")
    rid = _room_id()
    client.post(
        f"/files/upload?room_id={rid}",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("listed.txt", io.BytesIO(b"abc"), "text/plain")},
    )
    files = client.get(f"/files/room/{rid}", headers={"Authorization": f"Bearer {token}"}).json()
    names = [f["original_name"] for f in files]
    assert "listed.txt" in names


# ── Download with query-param token ──────────────────────────────────────────

def test_download_with_token_query_param_returns_200():
    """File download should work when token is passed as ?token= query param (for browser <a> links)."""
    token = _token("dl_qp_user")
    content = b"query param auth test"
    upload_resp = client.post(
        f"/files/upload?room_id={_room_id()}",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("qp_test.txt", io.BytesIO(content), "text/plain")},
    )
    file_id = upload_resp.json()["id"]
    # Use query param instead of Authorization header
    dl_resp = client.get(f"/files/download/{file_id}?token={token}")
    assert dl_resp.status_code == 200
    assert dl_resp.content == content


def test_download_without_any_token_returns_401():
    """Download with no token (no header, no query param) must return 401."""
    resp = client.get("/files/download/1")
    assert resp.status_code == 401
