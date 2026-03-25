# tests/test_main.py — Tests for app/main.py (lifespan, health, ready, exception handler)
"""
Tests for:
- Lifespan startup/shutdown (admin seeding, Kafka init/close)
- /health endpoint
- /ready endpoint branches (DB ok/fail, Redis ok/fail, Kafka ok/degraded)
- Global exception handler

Note: Database migrations are handled by the db-init container, not on startup.
"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ── Lifespan tests ────────────────────────────────────────────────────


class TestLifespan:
    """Tests for the lifespan context manager (startup/shutdown)."""

    @pytest.mark.asyncio
    async def test_lifespan_seeds_admin_and_starts_kafka(self):
        """Verify lifespan seeds admin user and starts Kafka producer."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.user_dal") as mock_dal, \
             patch("app.main.init_producer", new_callable=AsyncMock) as mock_init, \
             patch("app.main.close_producer", new_callable=AsyncMock) as mock_close, \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "changeme"), \
             patch("app.main.APP_ENV", "dev"), \
             patch("app.main.SECRET_KEY", "test-secret"):

            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_dal.get_by_username.return_value = None

            async with lifespan(mock_app):
                mock_init.assert_awaited_once()

            mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_handles_admin_seed_failure(self):
        """When admin seeding fails, startup should continue."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.init_producer", new_callable=AsyncMock), \
             patch("app.main.close_producer", new_callable=AsyncMock), \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "changeme"), \
             patch("app.main.APP_ENV", "dev"), \
             patch("app.main.SECRET_KEY", "test-secret"):

            # Session raises an exception during admin seeding
            mock_session_cls.return_value.__enter__ = MagicMock(
                side_effect=Exception("DB connection failed")
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            async with lifespan(mock_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_promotes_existing_admin(self):
        """When admin user exists but is not admin, promote them."""
        from app.main import lifespan

        mock_app = MagicMock()
        mock_user = MagicMock()
        mock_user.is_global_admin = False

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.user_dal") as mock_dal, \
             patch("app.main.init_producer", new_callable=AsyncMock), \
             patch("app.main.close_producer", new_callable=AsyncMock), \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "changeme"), \
             patch("app.main.APP_ENV", "dev"), \
             patch("app.main.SECRET_KEY", "test-secret"):

            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_dal.get_by_username.return_value = mock_user

            async with lifespan(mock_app):
                assert mock_user.is_global_admin is True
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_lifespan_warns_default_secret_key_in_dev(self):
        """In dev mode with default secret key, should log a warning but not error."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.user_dal") as mock_dal, \
             patch("app.main.init_producer", new_callable=AsyncMock), \
             patch("app.main.close_producer", new_callable=AsyncMock), \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "safe_password"), \
             patch("app.main.APP_ENV", "dev"), \
             patch("app.main.SECRET_KEY", "change-this-in-production"), \
             patch("app.main.logger") as mock_logger:

            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_dal.get_by_username.return_value = MagicMock(is_global_admin=True)

            async with lifespan(mock_app):
                mock_logger.warning.assert_any_call(
                    "default_secret_key", msg="Using default SECRET_KEY (acceptable for dev only)"
                )

    @pytest.mark.asyncio
    async def test_lifespan_errors_default_secret_key_in_prod(self):
        """In prod mode with default secret key, should log an error."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.user_dal") as mock_dal, \
             patch("app.main.init_producer", new_callable=AsyncMock), \
             patch("app.main.close_producer", new_callable=AsyncMock), \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "safe_password"), \
             patch("app.main.APP_ENV", "prod"), \
             patch("app.main.SECRET_KEY", "change-this-in-production"), \
             patch("app.main.logger") as mock_logger:

            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_dal.get_by_username.return_value = MagicMock(is_global_admin=True)

            async with lifespan(mock_app):
                mock_logger.error.assert_any_call(
                    "INSECURE_SECRET_KEY",
                    msg="SECRET_KEY is set to the default value! "
                    "Set a strong SECRET_KEY via environment variable before deploying.",
                )

    @pytest.mark.asyncio
    async def test_lifespan_errors_changeme_admin_password_in_prod(self):
        """In prod mode with 'changeme' admin password, should log an error."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.Session") as mock_session_cls, \
             patch("app.main.user_dal") as mock_dal, \
             patch("app.main.init_producer", new_callable=AsyncMock), \
             patch("app.main.close_producer", new_callable=AsyncMock), \
             patch("app.main.ADMIN_USERNAME", "admin"), \
             patch("app.main.ADMIN_PASSWORD", "changeme"), \
             patch("app.main.APP_ENV", "prod"), \
             patch("app.main.SECRET_KEY", "strong-production-key"), \
             patch("app.main.logger") as mock_logger:

            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_dal.get_by_username.return_value = MagicMock(is_global_admin=True)

            async with lifespan(mock_app):
                mock_logger.error.assert_any_call(
                    "INSECURE_ADMIN_PASSWORD",
                    msg="ADMIN_PASSWORD is 'changeme'! Set a strong password via environment variable.",
                )


# ── /ready endpoint branches ──────────────────────────────────────────


class TestReadyEndpoint:
    """Tests for GET /ready with various service states."""

    def test_ready_database_failure(self, client):
        """When DB is down, /ready should return 503."""
        with patch("app.main.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.execute.side_effect = Exception("DB connection refused")
            mock_session_cls.return_value = mock_session

            with patch("app.main.is_kafka_available", return_value=True):
                resp = client.get("/ready")
                assert resp.status_code == 503
                assert resp.json()["status"] == "not_ready"

    def test_ready_redis_failure(self, client):
        """When Redis is down, /ready should return 503."""
        with patch("app.main.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_redis = MagicMock()
            mock_redis.ping.side_effect = Exception("Redis connection refused")

            with patch("app.infrastructure.redis.get_redis", return_value=mock_redis), \
                 patch("app.main.is_kafka_available", return_value=True):
                resp = client.get("/ready")
                assert resp.status_code == 503
                data = resp.json()
                assert "redis" in data

    def test_ready_kafka_degraded(self, client):
        """When Kafka is unavailable, /ready should still be 200 (Kafka is optional)."""
        with patch("app.main.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_redis = MagicMock()
            mock_redis.ping.return_value = True

            with patch("app.infrastructure.redis.get_redis", return_value=mock_redis), \
                 patch("app.main.is_kafka_available", return_value=False):
                resp = client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["kafka"] == "degraded"

    def test_ready_kafka_exception(self, client):
        """When Kafka check itself throws, /ready should handle it."""
        with patch("app.main.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_redis = MagicMock()
            mock_redis.ping.return_value = True

            with patch("app.infrastructure.redis.get_redis", return_value=mock_redis), \
                 patch("app.main.is_kafka_available", side_effect=Exception("kafka error")):
                resp = client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert "degraded" in data["kafka"]

    def test_ready_all_services_ok(self, client):
        """When all services are ok, /ready should return 200."""
        with patch("app.main.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_redis = MagicMock()
            mock_redis.ping.return_value = True

            with patch("app.infrastructure.redis.get_redis", return_value=mock_redis), \
                 patch("app.main.is_kafka_available", return_value=True):
                resp = client.get("/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ready"
                assert data["database"] == "ok"
                assert data["redis"] == "ok"
                assert data["kafka"] == "ok"


# ── Global exception handler ─────────────────────────────────────────


class TestGlobalExceptionHandler:
    """Tests for the global exception handler."""

    def test_unhandled_exception_returns_500(self, client):
        """When an endpoint raises an unexpected exception, return 500 with generic message."""
        from app.main import app as test_app

        @test_app.get("/test-error")
        def raise_error():
            raise RuntimeError("Something went horribly wrong")

        resp = client.get("/test-error")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"


# -- Health check integration tests --------------------------------------------


class TestHealth:
    """Integration tests for /health and /ready endpoints."""

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ready_returns_status(self, client):
        """Readiness check -- in test environment with SQLite (no real Redis/Kafka),
        it should still return a response (may be 503 if Redis mock isn't wired for ping)."""
        resp = client.get("/ready")
        # In test environment, DB is available (SQLite), but Redis and Kafka may report degraded
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "database" in data
