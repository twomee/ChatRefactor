# tests/test_core_config.py — Unit tests for app/core/config.py
"""
Tests for:
- _require_env fail-fast in production mode
- DATABASE_URL fail-fast in production mode
- Default values in non-prod mode

Note: load_dotenv is patched out in reload tests so the .env file
doesn't override the test environment variables.
"""

import importlib
import os
from unittest.mock import patch

import pytest


class TestRequireEnv:
    """Tests for _require_env behavior in prod vs dev."""

    def test_require_env_exits_in_prod_when_missing(self):
        """In prod mode, missing required env var should call sys.exit."""
        env = {k: v for k, v in os.environ.items()}
        env["APP_ENV"] = "prod"
        env.pop("SECRET_KEY", None)

        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            with pytest.raises(SystemExit):
                import app.core.config as config_mod

                importlib.reload(config_mod)

    def test_require_env_returns_empty_in_dev_when_missing(self):
        """In dev mode, missing env var should return empty string."""
        env = {k: v for k, v in os.environ.items()}
        env["APP_ENV"] = "dev"
        env.pop("SECRET_KEY", None)
        env.pop("ADMIN_USERNAME", None)
        env.pop("ADMIN_PASSWORD", None)

        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            import app.core.config as config_mod

            importlib.reload(config_mod)
            assert config_mod.ADMIN_USERNAME == ""

    def test_database_url_exits_in_prod_when_empty(self):
        """In prod mode, empty DATABASE_URL should call sys.exit."""
        env = {k: v for k, v in os.environ.items()}
        env["APP_ENV"] = "prod"
        env["SECRET_KEY"] = "test-secret"
        env["DATABASE_URL"] = ""
        env["ADMIN_USERNAME"] = "admin"
        env["ADMIN_PASSWORD"] = "password"

        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            with pytest.raises(SystemExit):
                import app.core.config as config_mod

                importlib.reload(config_mod)
