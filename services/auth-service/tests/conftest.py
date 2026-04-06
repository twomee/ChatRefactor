# tests/conftest.py — pytest fixtures for auth service tests
"""
Sets up:
- SQLite in-memory database (replaces PostgreSQL for tests)
- Overrides get_db dependency to use test database
- Mocks Redis (token blacklist)
- Mocks Kafka producer (event production)
- httpx.AsyncClient for async test requests

Key design decisions:
- SQLite in-memory: fast, isolated, no external dependencies needed for tests
- Redis mock: avoids needing a real Redis instance; returns None for all gets
- Kafka mock: avoids needing a real Kafka cluster; produce_event always returns True
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the auth-service root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base, get_db
from app.main import app

# ── Test database setup ──────────────────────────────────────────────────

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Yield a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create all tables in the test database
Base.metadata.create_all(bind=test_engine)


# ── Mock Redis ───────────────────────────────────────────────────────────


class MockRedis:
    """In-memory mock for Redis. Tracks blacklisted tokens and 2FA temp tokens."""

    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def setex(self, key, ttl, value):
        self._store[key] = value

    def delete(self, key):
        """Remove a key from the store (used by 2FA single-use temp tokens)."""
        self._store.pop(key, None)

    def ping(self):
        return True

    def clear(self):
        self._store.clear()


_mock_redis = MockRedis()


def mock_get_redis():
    return _mock_redis


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test overrides for every test function.

    - Overrides get_db to use SQLite in-memory
    - Patches Redis to use in-memory mock
    - Patches Kafka produce_event to be a no-op
    - Sets TOTP_ENCRYPTION_KEY for encryption tests
    - Cleans up user table after each test
    """
    # Set encryption key for tests (64 hex chars = 32 bytes for AES-256)
    os.environ.setdefault(
        "TOTP_ENCRYPTION_KEY",
        "0" * 64,  # deterministic test key — never use in production
    )

    # Override FastAPI dependencies
    app.dependency_overrides[get_db] = override_get_db

    # Patch Redis
    with (
        patch("app.infrastructure.redis.get_redis", mock_get_redis),
        patch("app.core.security.get_redis", mock_get_redis, create=True),
        patch("app.services.two_factor_service.get_redis", mock_get_redis),
        patch(
            "app.infrastructure.kafka_producer.produce_event", return_value=True
        ) as _mock_kafka,
    ):
        # Also patch the import inside security.py's decode_token
        with patch("app.infrastructure.redis.redis_pool", MagicMock()):
            yield

    # Clean up: clear Redis mock and delete all users + reset tokens
    _mock_redis.clear()
    db = TestSessionLocal()
    try:
        from app.models import PasswordResetToken, User

        db.query(PasswordResetToken).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()

    # Clear dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Synchronous test client for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_redis_instance():
    """Direct access to the mock Redis instance for test assertions."""
    return _mock_redis


@pytest.fixture
def db_session():
    """Provide a clean database session for DAL-level tests.

    Yields a SQLAlchemy session connected to the in-memory test database.
    Rolls back any changes after each test to keep tests isolated.
    """
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        from app.models import PasswordResetToken, User

        db.query(PasswordResetToken).delete()
        db.query(User).delete()
        db.commit()
        db.close()
