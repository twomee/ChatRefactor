# tests/test_core_config.py — Tests for app/core/config.py
#
# Covers:
#   - _require_env in dev mode (returns empty string when var is missing)
#   - _require_env in prod mode (calls sys.exit when var is missing)
#   - _require_env when value is set (returns value in any env)
#   - DATABASE_URL prod validation
import importlib
import os
from unittest.mock import patch

import pytest


class TestRequireEnv:
    """Tests for the _require_env function."""

    def test_returns_value_when_set(self):
        """Should return the env var value when it is set."""
        with patch.dict(os.environ, {"TEST_VAR": "my-value"}):
            with patch("app.core.config.APP_ENV", "prod"):
                from app.core.config import _require_env

                result = _require_env("TEST_VAR")
                assert result == "my-value"

    def test_returns_empty_string_in_dev_when_missing(self):
        """In dev mode, should return empty string when env var is missing."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if it exists
            os.environ.pop("NONEXISTENT_VAR", None)
            with patch("app.core.config.APP_ENV", "dev"):
                from app.core.config import _require_env

                result = _require_env("NONEXISTENT_VAR")
                assert result == ""

    def test_exits_in_prod_when_missing(self):
        """In prod mode, should call sys.exit(1) when env var is missing."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MISSING_PROD_VAR", None)
            with patch("app.core.config.APP_ENV", "prod"):
                from app.core.config import _require_env

                with pytest.raises(SystemExit) as exc_info:
                    _require_env("MISSING_PROD_VAR")
                assert exc_info.value.code == 1


class TestDatabaseUrlProdValidation:
    """Tests for the DATABASE_URL prod fail-fast logic."""

    def test_prod_without_database_url_exits(self):
        """In prod mode, missing DATABASE_URL should cause sys.exit(1).

        This test reloads the config module to trigger the module-level check,
        then restores the module state to avoid polluting other tests.
        """
        import app.core.config as config_module

        # Save original state
        original_secret_key = config_module.SECRET_KEY
        original_app_env = config_module.APP_ENV
        original_db_url = config_module.DATABASE_URL
        original_kafka = config_module.KAFKA_BOOTSTRAP_SERVERS
        original_auth_url = config_module.AUTH_SERVICE_URL
        original_algorithm = config_module.ALGORITHM

        env = {
            "APP_ENV": "prod",
            "SECRET_KEY": "prod-secret",
            "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
            "AUTH_SERVICE_URL": "http://auth:8001",
        }
        # Remove DATABASE_URL
        env_clean = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env_clean.update(env)

        try:
            with pytest.raises(SystemExit) as exc_info:
                with patch.dict(os.environ, env_clean, clear=True):
                    importlib.reload(config_module)

            assert exc_info.value.code == 1
        finally:
            # Restore the module state so other tests are not affected
            config_module.SECRET_KEY = original_secret_key
            config_module.APP_ENV = original_app_env
            config_module.DATABASE_URL = original_db_url
            config_module.KAFKA_BOOTSTRAP_SERVERS = original_kafka
            config_module.AUTH_SERVICE_URL = original_auth_url
            config_module.ALGORITHM = original_algorithm
