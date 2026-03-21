# tests/test_auth.py — comprehensive auth route tests
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from main import app

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=test_engine)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield


# ── Register ──────────────────────────────────────────────────────────────────


def test_register_returns_201():
    resp = client.post("/auth/register", json={"username": "alice", "password": "password123"})
    assert resp.status_code == 201
    assert resp.json()["message"] == "Registered successfully"


def test_register_duplicate_username_returns_409():
    client.post("/auth/register", json={"username": "bob", "password": "password123"})
    resp = client.post("/auth/register", json={"username": "bob", "password": "otherpass123"})
    assert resp.status_code == 409


def test_register_empty_username_returns_422():
    resp = client.post("/auth/register", json={"username": "  ", "password": "password123"})
    assert resp.status_code == 422


def test_register_empty_password_returns_422():
    resp = client.post("/auth/register", json={"username": "carol", "password": "  "})
    assert resp.status_code == 422


def test_register_missing_fields_returns_422():
    resp = client.post("/auth/register", json={"username": "dave"})
    assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_returns_token_and_username():
    client.post("/auth/register", json={"username": "eve", "password": "secretpass1"})
    resp = client.post("/auth/login", json={"username": "eve", "password": "secretpass1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == "eve"
    assert "is_global_admin" in data


def test_login_is_global_admin_false_for_regular_user():
    client.post("/auth/register", json={"username": "frank", "password": "password123"})
    resp = client.post("/auth/login", json={"username": "frank", "password": "password123"})
    assert resp.json()["is_global_admin"] is False


def test_login_wrong_password_returns_401():
    client.post("/auth/register", json={"username": "grace", "password": "correctpass1"})
    resp = client.post("/auth/login", json={"username": "grace", "password": "wrongpass99"})
    assert resp.status_code == 401


def test_login_unknown_user_returns_401():
    resp = client.post("/auth/login", json={"username": "nobody", "password": "password123"})
    assert resp.status_code == 401


def test_login_missing_fields_returns_422():
    resp = client.post("/auth/login", json={"username": "heidi"})
    assert resp.status_code == 422


# ── Token / protected endpoints ───────────────────────────────────────────────


def test_access_protected_endpoint_without_token_returns_401():
    resp = client.get("/rooms/")
    assert resp.status_code == 401


def test_access_protected_endpoint_with_invalid_token_returns_401():
    resp = client.get("/rooms/", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_access_protected_endpoint_with_valid_token_returns_200():
    client.post("/auth/register", json={"username": "ivan", "password": "password123"})
    token = client.post("/auth/login", json={"username": "ivan", "password": "password123"}).json()["access_token"]
    resp = client.get("/rooms/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
