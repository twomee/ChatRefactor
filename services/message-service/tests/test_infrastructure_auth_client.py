# tests/test_infrastructure_auth_client.py — Tests for app/infrastructure/auth_client.py
#
# Covers:
#   - Circuit breaker states (closed, open, half-open)
#   - HTTP call success (200), not found (404), server error (5xx)
#   - Timeout and connection errors with retry + backoff
#   - reset_circuit_breaker utility
#   - Username validation (SSRF prevention)
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.infrastructure import auth_client
from app.infrastructure.auth_client import (
    BACKOFF_BASE,
    FAILURE_THRESHOLD,
    MAX_RETRIES,
    RECOVERY_TIMEOUT,
    REQUEST_TIMEOUT,
    _is_circuit_open,
    _record_failure,
    _record_success,
    get_user_by_username,
    reset_circuit_breaker,
)


@pytest.fixture(autouse=True)
def _clean_circuit():
    """Reset circuit breaker state before and after every test."""
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


# ══════════════════════════════════════════════════════════════════════
# Circuit breaker unit tests
# ══════════════════════════════════════════════════════════════════════


class TestCircuitBreakerState:
    """Tests for the circuit breaker helper functions."""

    def test_circuit_initially_closed(self):
        """Circuit should be closed (not open) when no failures recorded."""
        assert _is_circuit_open() is False

    def test_circuit_stays_closed_below_threshold(self):
        """Circuit should remain closed when failures are below threshold."""
        for _ in range(FAILURE_THRESHOLD - 1):
            _record_failure()
        assert _is_circuit_open() is False

    def test_circuit_opens_at_threshold(self):
        """Circuit should open once consecutive failures reach the threshold."""
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()
        assert _is_circuit_open() is True

    def test_circuit_half_open_after_recovery_timeout(self):
        """After RECOVERY_TIMEOUT elapses, circuit should transition to half-open
        (allows probe request through)."""
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()
        assert _is_circuit_open() is True

        # Fast-forward the circuit_open_since time
        auth_client._circuit_open_since = time.monotonic() - RECOVERY_TIMEOUT - 1
        assert _is_circuit_open() is False

    def test_record_success_closes_circuit(self):
        """A successful call should close the circuit and reset failure count."""
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()
        assert _is_circuit_open() is True

        _record_success()
        assert _is_circuit_open() is False
        assert auth_client._consecutive_failures == 0
        assert auth_client._circuit_open_since is None

    def test_reset_circuit_breaker(self):
        """reset_circuit_breaker should clear all state."""
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()
        assert _is_circuit_open() is True

        reset_circuit_breaker()
        assert _is_circuit_open() is False
        assert auth_client._consecutive_failures == 0
        assert auth_client._circuit_open_since is None


# ══════════════════════════════════════════════════════════════════════
# get_user_by_username — HTTP call tests
# ══════════════════════════════════════════════════════════════════════


class TestGetUserByUsername:
    """Tests for the HTTP call to the auth service."""

    @pytest.mark.asyncio
    async def test_returns_user_on_200(self):
        """Should return user dict on HTTP 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 42, "username": "alice"}

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_user_by_username("alice")

        assert result == {"id": 42, "username": "alice"}

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        """Should return None for user not found (HTTP 404)."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_user_by_username("nobody")

        assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_server_error(self):
        """Should retry on 5xx responses and eventually raise ConnectionError."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.infrastructure.auth_client.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(ConnectionError, match="unreachable"):
                    await get_user_by_username("someone")

            # Verify it was called MAX_RETRIES times
            assert mock_client.get.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self):
        """Should retry on httpx.TimeoutException and raise after exhausting retries."""
        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.infrastructure.auth_client.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(ConnectionError, match="unreachable"):
                    await get_user_by_username("someone")

            assert mock_client.get.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retries_on_connect_error(self):
        """Should retry on httpx.ConnectError and raise after exhausting retries."""
        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.infrastructure.auth_client.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(ConnectionError, match="unreachable"):
                    await get_user_by_username("someone")

            assert mock_client.get.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_circuit_open_rejects_immediately(self):
        """When circuit is open, should raise ConnectionError without making HTTP call."""
        # Open the circuit
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ConnectionError, match="circuit breaker is open"):
                await get_user_by_username("anyone")

            # Should NOT have made any HTTP calls
            mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_after_timeout_recovery(self):
        """After recovery timeout, a probe request that succeeds should close the circuit."""
        # Open the circuit
        for _ in range(FAILURE_THRESHOLD):
            _record_failure()
        assert _is_circuit_open() is True

        # Simulate recovery timeout elapsed
        auth_client._circuit_open_since = time.monotonic() - RECOVERY_TIMEOUT - 1

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "username": "probe"}

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_user_by_username("probe")

        assert result == {"id": 1, "username": "probe"}
        assert _is_circuit_open() is False  # Circuit should be closed now

    @pytest.mark.asyncio
    async def test_record_failure_called_on_all_retries_exhausted(self):
        """When all retries are exhausted, _record_failure should be called."""
        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.infrastructure.auth_client.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(ConnectionError):
                    await get_user_by_username("fail")

        # After one failure, consecutive_failures should be incremented
        assert auth_client._consecutive_failures == 1


# ══════════════════════════════════════════════════════════════════════
# Security: username validation (SSRF prevention)
# ══════════════════════════════════════════════════════════════════════


class TestUsernameValidation:
    """Tests for username validation to prevent SSRF and path traversal."""

    @pytest.mark.asyncio
    async def test_rejects_empty_username(self):
        """Should return None for empty username."""
        result = await get_user_by_username("")
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self):
        """Should return None for usernames containing path traversal sequences."""
        result = await get_user_by_username("../../admin")
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_url_encoded_traversal(self):
        """Should return None for usernames with slashes."""
        result = await get_user_by_username("admin/../../etc/passwd")
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_special_characters(self):
        """Should return None for usernames with special characters."""
        result = await get_user_by_username("user;DROP TABLE users")
        assert result is None

    @pytest.mark.asyncio
    async def test_accepts_valid_username(self):
        """Should allow alphanumeric usernames with underscores, hyphens, dots."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "username": "valid_user-123.test"}

        with patch("app.infrastructure.auth_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_user_by_username("valid_user-123.test")

        assert result == {"id": 1, "username": "valid_user-123.test"}
