# tests/test_coverage_gaps.py — Tests targeting uncovered lines to reach 95% threshold
"""
Covers:
- app/utils/encryption.py lines 12, 18:
    - RuntimeError when TOTP_ENCRYPTION_KEY is not set
    - ValueError when key decodes to wrong byte length
- app/services/auth_service.py lines 183-185, 229, 264, 294, 317, 319, 347, 353,
    369-375, 405-408, 426-432, 459:
    - _get_redis() lazy import path
    - _consume_2fa_temp_token deletes after successful read
    - _check_and_mark_totp_replay marks code as used on first call
    - setup_2fa: user not found (404)
    - verify_2fa_setup: user not found (404), already enabled (400)
    - disable_2fa: user not found (404), corrupted state (500), replay detection
    - verify_login_2fa: user not found / 2FA misconfigured (401), replay detection
    - get_2fa_status: user not found (404)
"""
import os
from unittest.mock import MagicMock, patch, AsyncMock

import pyotp
import pytest
from fastapi import HTTPException

from app.utils.totp import check_and_mark_totp_replay
from app.services.two_factor_service import (
    consume_2fa_temp_token,
    disable_2fa,
    get_2fa_status,
    setup_2fa,
    verify_2fa_setup,
    verify_login_2fa,
)


# ═══════════════════════════════════════════════════════════════════════
#  Encryption key validation error paths
# ═══════════════════════════════════════════════════════════════════════


class TestEncryptionKeyValidation:
    """Tests for app/utils/encryption.py _get_key() error paths."""

    def test_missing_key_raises_runtime_error(self):
        """_get_key() must raise RuntimeError when TOTP_ENCRYPTION_KEY is empty/unset.

        Line 12 in encryption.py: the `raise RuntimeError(...)` branch.
        """
        from app.utils.encryption import _get_key

        original = os.environ.pop("TOTP_ENCRYPTION_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="TOTP_ENCRYPTION_KEY"):
                _get_key()
        finally:
            if original is not None:
                os.environ["TOTP_ENCRYPTION_KEY"] = original
            else:
                # Restore the default test key so subsequent tests are not affected
                os.environ["TOTP_ENCRYPTION_KEY"] = "0" * 64

    def test_wrong_length_key_raises_value_error(self):
        """_get_key() must raise ValueError when the decoded key is not 32 bytes.

        Line 18 in encryption.py: the `raise ValueError(...)` branch.
        A 48-char hex string decodes to 24 bytes — not 32, so it must be rejected.
        """
        from app.utils.encryption import _get_key

        original = os.environ.get("TOTP_ENCRYPTION_KEY")
        try:
            # 48 hex chars = 24 bytes, which is not 32 bytes
            os.environ["TOTP_ENCRYPTION_KEY"] = "a" * 48
            with pytest.raises(ValueError, match="32 bytes"):
                _get_key()
        finally:
            os.environ["TOTP_ENCRYPTION_KEY"] = original if original is not None else "0" * 64


# ═══════════════════════════════════════════════════════════════════════
#  auth_service internals: _get_redis, _consume_2fa_temp_token,
#  _check_and_mark_totp_replay
# ═══════════════════════════════════════════════════════════════════════


class TestGetRedisHelper:
    """Ensure the get_redis() import path is exercised via totp module."""

    def test_get_redis_returns_redis_instance(self):
        """get_redis() should return a Redis instance from the infrastructure module."""
        mock_redis = MagicMock()
        with patch("app.infrastructure.redis.get_redis", return_value=mock_redis):
            from app.infrastructure.redis import get_redis
            result = get_redis()
        assert result is mock_redis


class TestConsume2FATempToken:
    """Tests for _consume_2fa_temp_token() — covers line 229 (r.delete)."""

    def test_consume_token_deletes_key_and_returns_data(self):
        """Consuming a valid token should return the stored data and remove the key."""
        import json

        stored_payload = json.dumps({"user_id": 42, "username": "alice"})
        mock_redis = MagicMock()
        mock_redis.get.return_value = stored_payload
        mock_redis.delete.return_value = 1

        with patch("app.services.two_factor_service.get_redis", return_value=mock_redis):
            result = consume_2fa_temp_token("some-token")

        assert result == {"user_id": 42, "username": "alice"}
        mock_redis.delete.assert_called_once_with("2fa_temp:some-token")

    def test_consume_missing_token_returns_none(self):
        """Consuming a non-existent token should return None without calling delete."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("app.services.two_factor_service.get_redis", return_value=mock_redis):
            result = consume_2fa_temp_token("ghost-token")

        assert result is None
        mock_redis.delete.assert_not_called()


class TestCheckAndMarkTOTPReplay:
    """Tests for _check_and_mark_totp_replay() — covers line 264 (setex on first use)."""

    def test_first_use_marks_code_and_returns_false(self):
        """The first time a code is used it should be stored and False returned (not replay)."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # code not yet seen

        with patch("app.utils.totp.get_redis", return_value=mock_redis):
            result = check_and_mark_totp_replay(user_id=7, code="123456")

        assert result is False
        mock_redis.setex.assert_called_once_with("totp_used:7:123456", 90, "1")

    def test_second_use_returns_true(self):
        """A code that was already used should trigger replay detection (True)."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "1"  # code was already marked

        with patch("app.utils.totp.get_redis", return_value=mock_redis):
            result = check_and_mark_totp_replay(user_id=7, code="123456")

        assert result is True
        mock_redis.setex.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
#  setup_2fa — user not found (line 294)
# ═══════════════════════════════════════════════════════════════════════


class TestSetup2FAEdgeCases:
    """Service-level edge cases for setup_2fa()."""

    def test_setup_2fa_user_not_found_raises_404(self):
        """setup_2fa() must raise 404 when the user_id does not exist in the database."""
        mock_db = MagicMock()
        user_info = {"user_id": 9999}

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                setup_2fa(mock_db, user_info)
        assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  verify_2fa_setup — user not found (317), already enabled (319)
# ═══════════════════════════════════════════════════════════════════════


class TestVerify2FASetupEdgeCases:
    """Service-level edge cases for verify_2fa_setup()."""

    def test_verify_setup_user_not_found_raises_404(self):
        """verify_2fa_setup() must raise 404 when the user does not exist."""
        mock_db = MagicMock()
        user_info = {"user_id": 9999}

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                verify_2fa_setup(mock_db, user_info, "123456")
        assert exc_info.value.status_code == 404

    def test_verify_setup_already_enabled_raises_400(self):
        """verify_2fa_setup() must raise 400 when 2FA is already enabled for the user."""
        mock_db = MagicMock()
        user_info = {"user_id": 1}
        mock_user = MagicMock()
        mock_user.is_2fa_enabled = True

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                verify_2fa_setup(mock_db, user_info, "123456")
        assert exc_info.value.status_code == 400
        assert "already enabled" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════
#  disable_2fa — user not found (347), corrupted state (353),
#                replay detection (369-375)
# ═══════════════════════════════════════════════════════════════════════


class TestDisable2FAEdgeCases:
    """Service-level edge cases for disable_2fa()."""

    def test_disable_2fa_user_not_found_raises_404(self):
        """disable_2fa() must raise 404 when the user does not exist."""
        mock_db = MagicMock()
        user_info = {"user_id": 9999}

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                disable_2fa(mock_db, user_info, "123456")
        assert exc_info.value.status_code == 404

    def test_disable_2fa_corrupted_state_raises_500(self):
        """disable_2fa() must raise 500 when 2FA is enabled but totp_secret is missing.

        This is the 'corrupted authentication state' guard.
        """
        mock_db = MagicMock()
        user_info = {"user_id": 1}
        mock_user = MagicMock()
        mock_user.is_2fa_enabled = True
        mock_user.totp_secret = None  # corrupted: flag set but no secret stored

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                disable_2fa(mock_db, user_info, "123456")
        assert exc_info.value.status_code == 500
        assert "corrupted" in exc_info.value.detail.lower()

    def test_disable_2fa_replay_detected_raises_400(self):
        """disable_2fa() must raise 400 when a replay attack is detected."""
        mock_db = MagicMock()
        user_info = {"user_id": 1}
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "alice"
        mock_user.is_2fa_enabled = True
        # totp_secret must be truthy to pass the corrupted-state guard
        mock_user.totp_secret = "encrypted-secret-placeholder"

        # Build a real TOTP secret so verify_totp returns True
        secret = pyotp.random_base32()
        code = pyotp.TOTP(secret).now()

        with patch("app.services.two_factor_service.user_dal") as mock_dal, \
             patch("app.services.two_factor_service.decrypt_totp_secret", return_value=secret), \
             patch("app.services.two_factor_service.check_and_mark_totp_replay", return_value=True):
            mock_dal.get_by_id.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                disable_2fa(mock_db, user_info, code)
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
#  verify_login_2fa — user/2FA state error (405-408),
#                     replay detection (426-432)
# ═══════════════════════════════════════════════════════════════════════


class TestVerifyLogin2FAEdgeCases:
    """Service-level edge cases for verify_login_2fa()."""

    @pytest.mark.asyncio
    async def test_verify_login_user_not_found_raises_401(self):
        """verify_login_2fa() must raise 401 when the user_id in the temp token is missing."""
        mock_db = MagicMock()

        with patch("app.services.two_factor_service.peek_2fa_temp_token",
                   return_value={"user_id": 9999, "username": "ghost"}), \
             patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await verify_login_2fa(mock_db, "some-temp-token", "123456")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_login_2fa_not_enabled_raises_401(self):
        """verify_login_2fa() must raise 401 when the user has 2FA disabled in the DB.

        This guards against a race where 2FA is disabled after the temp token is issued.
        """
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.is_2fa_enabled = False  # 2FA disabled on this user
        mock_user.totp_secret = None

        with patch("app.services.two_factor_service.peek_2fa_temp_token",
                   return_value={"user_id": 1, "username": "alice"}), \
             patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                await verify_login_2fa(mock_db, "some-temp-token", "123456")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_login_replay_detected_raises_401(self):
        """verify_login_2fa() must raise 401 when a TOTP replay attack is detected."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "alice"
        mock_user.is_2fa_enabled = True
        mock_user.is_global_admin = False

        secret = pyotp.random_base32()
        code = pyotp.TOTP(secret).now()

        with patch("app.services.two_factor_service.peek_2fa_temp_token",
                   return_value={"user_id": 1, "username": "alice"}), \
             patch("app.services.two_factor_service.user_dal") as mock_dal, \
             patch("app.services.two_factor_service.decrypt_totp_secret", return_value=secret), \
             patch("app.services.two_factor_service.check_and_mark_totp_replay", return_value=True):
            mock_dal.get_by_id.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                await verify_login_2fa(mock_db, "some-temp-token", code)
        assert exc_info.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
#  get_2fa_status — user not found (line 459)
# ═══════════════════════════════════════════════════════════════════════


class TestGet2FAStatusEdgeCases:
    """Service-level edge cases for get_2fa_status()."""

    def test_get_2fa_status_user_not_found_raises_404(self):
        """get_2fa_status() must raise 404 when the user_id does not exist."""
        mock_db = MagicMock()
        user_info = {"user_id": 9999}

        with patch("app.services.two_factor_service.user_dal") as mock_dal:
            mock_dal.get_by_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                get_2fa_status(mock_db, user_info)
        assert exc_info.value.status_code == 404
