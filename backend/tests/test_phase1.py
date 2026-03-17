# tests/test_phase1.py
import sys
import os
import pytest

# Add backend/ to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from main import app

# Use an in-memory SQLite DB for tests — StaticPool keeps all sessions on one connection
TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
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

# Create tables and seed data before tests
Base.metadata.create_all(bind=test_engine)
with TestSessionLocal() as db:
    from auth import hash_password
    from config import ADMIN_USERNAME, ADMIN_PASSWORD
    for room_name in ["politics", "sports", "movies"]:
        if not db.query(models.Room).filter(models.Room.name == room_name).first():
            db.add(models.Room(name=room_name))
    if not db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
        db.add(models.User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_global_admin=True,
        ))
    db.commit()

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


def test_register_success():
    """User registration returns 201."""
    resp = client.post("/auth/register", json={"username": "testuser", "password": "secret123"})
    assert resp.status_code == 201
    assert resp.json()["message"] == "Registered successfully"


def test_duplicate_registration_rejected():
    """Second registration with the same username returns 409."""
    client.post("/auth/register", json={"username": "dupuser", "password": "pass"})
    resp = client.post("/auth/register", json={"username": "dupuser", "password": "otherpass"})
    assert resp.status_code == 409


def test_login_correct_credentials():
    """Login with correct credentials returns 200 and an access_token."""
    client.post("/auth/register", json={"username": "loginuser", "password": "mypassword"})
    resp = client.post("/auth/login", json={"username": "loginuser", "password": "mypassword"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == "loginuser"


def test_login_wrong_password():
    """Login with wrong password returns 401."""
    client.post("/auth/register", json={"username": "wrongpassuser", "password": "correct"})
    resp = client.post("/auth/login", json={"username": "wrongpassuser", "password": "wrong"})
    assert resp.status_code == 401


def test_list_rooms_authenticated():
    """GET /rooms/ with a valid token returns the 3 seeded rooms."""
    # Register + login to get token
    client.post("/auth/register", json={"username": "roomtester", "password": "pass123"})
    login_resp = client.post("/auth/login", json={"username": "roomtester", "password": "pass123"})
    token = login_resp.json()["access_token"]

    resp = client.get("/rooms/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    rooms = resp.json()
    assert isinstance(rooms, list)
    room_names = [r["name"] for r in rooms]
    assert "politics" in room_names
    assert "sports" in room_names
    assert "movies" in room_names
