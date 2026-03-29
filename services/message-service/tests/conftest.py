# tests/conftest.py — Shared test fixtures
#
# Uses SQLite in-memory for fast, isolated tests.
# Mocks Kafka (no real broker needed) and Auth Service (no real HTTP calls).
import os
import sys

# Ensure app modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set test environment before importing app modules
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:29092"
os.environ["AUTH_SERVICE_URL"] = "http://localhost:8001"

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.database import Base, get_db
from app.models import Message

# ── In-memory SQLite test database ──────────────────────────────────

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Create all tables
Base.metadata.create_all(bind=test_engine)


@pytest.fixture()
def db():
    """Yield a test DB session with automatic rollback after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """FastAPI test client with the DB session overridden to use SQLite.
    Patches Kafka and Alembic so lifespan doesn't block on real connections."""

    def _override_get_db():
        yield db

    # Patch Kafka so lifespan doesn't try to connect
    with (
        patch("app.main.init_producer", new_callable=AsyncMock),
        patch("app.main.close_producer", new_callable=AsyncMock),
        patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
        patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
    ):
        from app.main import app

        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

        app.dependency_overrides.clear()


# ── JWT token fixtures ──────────────────────────────────────────────


def _create_test_token(user_id: int = 1, username: str = "testuser", expired: bool = False) -> str:
    """Create a JWT token for testing."""
    exp = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=24))
    payload = {"sub": str(user_id), "username": username, "exp": exp}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture()
def auth_headers() -> dict:
    """Valid Authorization headers for a test user."""
    token = _create_test_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def expired_auth_headers() -> dict:
    """Expired Authorization headers."""
    token = _create_test_token(expired=True)
    return {"Authorization": f"Bearer {token}"}


# ── Sample data fixtures ────────────────────────────────────────────


@pytest.fixture()
def sample_messages(db) -> list[Message]:
    """Insert a set of sample messages for room_id=1."""
    messages = []
    base_time = datetime(2025, 1, 1, 12, 0, 0)
    for i in range(5):
        msg = Message(
            message_id=f"msg-{i:03d}",
            sender_id=1,
            room_id=1,
            content=f"Test message {i}",
            is_private=False,
            sent_at=base_time + timedelta(minutes=i),
        )
        db.add(msg)
        messages.append(msg)
    db.commit()
    for m in messages:
        db.refresh(m)
    return messages


@pytest.fixture()
def consumer():
    """Create a MessagePersistenceConsumer instance for testing."""
    from app.consumers.persistence_consumer import MessagePersistenceConsumer

    return MessagePersistenceConsumer()
