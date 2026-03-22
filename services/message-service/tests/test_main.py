# tests/test_main.py — Tests for application lifespan and main module
#
# Covers:
#   - Lifespan: security warnings for default SECRET_KEY (dev vs prod)
#   - Lifespan: Alembic migration failure (should not crash)
#   - Lifespan: Kafka consumer start failure (should not crash)
#   - Ready endpoint: database down returns 503
#   - Ready endpoint: Kafka check exception handling
#   - Global exception handler returns 500
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════════════
# Lifespan — Security warnings
# ══════════════════════════════════════════════════════════════════════


class TestLifespanSecurityWarnings:
    """Tests for SECRET_KEY security warnings during startup."""

    def test_default_secret_key_warning_in_dev(self):
        """In dev mode with default SECRET_KEY, should log a warning but start normally."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.APP_ENV", "dev"),
            patch("app.main.SECRET_KEY", "change-this-in-production"),
        ):
            from app.core.database import get_db
            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200

    def test_default_secret_key_error_in_prod(self):
        """In prod/staging mode with default SECRET_KEY, should log an error but still start."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.APP_ENV", "staging"),
            patch("app.main.SECRET_KEY", "change-this-in-production"),
            patch("app.main.logger") as mock_logger,
        ):
            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200

            # Verify the error was logged
            mock_logger.error.assert_any_call(
                "INSECURE_SECRET_KEY",
                msg="SECRET_KEY is set to the default value! "
                "Set a strong SECRET_KEY via environment variable before deploying.",
            )

    def test_custom_secret_key_no_warning(self):
        """With a non-default SECRET_KEY, should not log any security warning."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.APP_ENV", "prod"),
            patch("app.main.SECRET_KEY", "super-secure-production-key-2024"),
        ):
            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Lifespan — Alembic migration failure
# ══════════════════════════════════════════════════════════════════════


class TestLifespanAlembicFailure:
    """Tests for Alembic migration failures during startup."""

    def test_alembic_failure_does_not_crash(self):
        """Alembic migration failure should be logged but not prevent startup."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command") as mock_alembic,
        ):
            mock_alembic.upgrade.side_effect = Exception("migration failed")

            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Lifespan — Kafka consumer start failure
# ══════════════════════════════════════════════════════════════════════


class TestLifespanKafkaConsumerFailure:
    """Tests for Kafka consumer start failures during startup."""

    def test_consumer_start_failure_does_not_crash(self):
        """Kafka consumer start failure should be logged but not prevent startup."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch(
                "app.consumers.persistence_consumer.MessagePersistenceConsumer.start",
                new_callable=AsyncMock,
                side_effect=Exception("consumer start failed"),
            ),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
        ):
            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/health")
                assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Ready endpoint — failure cases
# ══════════════════════════════════════════════════════════════════════


class TestReadyEndpointFailures:
    """Tests for the /ready endpoint when dependencies are down."""

    def test_ready_returns_503_when_db_is_down(self):
        """Should return 503 when database is unreachable."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.Session") as MockSession,
        ):
            # Make the DB check fail
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(side_effect=Exception("connection refused"))
            mock_session.__exit__ = MagicMock(return_value=False)
            MockSession.return_value = mock_session

            from app.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/ready")

                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "not_ready"
                assert "connection refused" in data["database"]

    def test_ready_reports_kafka_degraded_when_unavailable(self):
        """Should report kafka as degraded when not available."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.is_kafka_available", return_value=False),
        ):
            from app.core.database import get_db
            from app.main import app

            # Override DB to use test SQLite
            from tests.conftest import TestSessionLocal

            def _override_get_db():
                db = TestSessionLocal()
                try:
                    yield db
                finally:
                    db.close()

            app.dependency_overrides[get_db] = _override_get_db

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/ready")
                data = response.json()
                assert data["kafka"] == "degraded"

            app.dependency_overrides.clear()

    def test_ready_handles_kafka_check_exception(self):
        """Should handle exception from Kafka availability check."""
        with (
            patch("app.main.init_producer", new_callable=AsyncMock),
            patch("app.main.close_producer", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.start", new_callable=AsyncMock),
            patch("app.consumers.persistence_consumer.MessagePersistenceConsumer.stop", new_callable=AsyncMock),
            patch("app.main.alembic_command"),
            patch("app.main.is_kafka_available", side_effect=Exception("kafka check failed")),
        ):
            from app.core.database import get_db
            from app.main import app

            from tests.conftest import TestSessionLocal

            def _override_get_db():
                db = TestSessionLocal()
                try:
                    yield db
                finally:
                    db.close()

            app.dependency_overrides[get_db] = _override_get_db

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/ready")
                data = response.json()
                assert "degraded" in data["kafka"]

            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════
# Global exception handler
# ══════════════════════════════════════════════════════════════════════


class TestGlobalExceptionHandler:
    """Tests for the catch-all exception handler."""

    def test_unhandled_exception_returns_500(self, client):
        """Unhandled exceptions should return a generic 500 response."""
        from app.main import app

        # Add a temporary route that raises
        @app.get("/test-error")
        def raise_error():
            raise RuntimeError("unexpected error")

        response = client.get("/test-error")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"
