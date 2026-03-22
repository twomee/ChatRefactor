# app/infrastructure/auth_client.py — HTTP client for Auth Service
#
# Used by the Kafka consumer to resolve usernames to user IDs when persisting
# private messages. The monolith could do a direct DB lookup (user_dal.get_by_username),
# but in the microservice world, user data lives in the auth-service's database.
#
# Circuit breaker pattern:
#   - Tracks consecutive failures to the auth service
#   - After FAILURE_THRESHOLD consecutive failures, opens the circuit (rejects immediately)
#   - After RECOVERY_TIMEOUT seconds, allows a single probe request
#   - If the probe succeeds, closes the circuit; if it fails, resets the timer
#
# This prevents cascading failures: if the auth service is down, we don't want
# every private message to hang for the full timeout before failing.
import asyncio
import re
import time
from urllib.parse import quote

import httpx

from app.core.config import AUTH_SERVICE_URL
from app.core.logging import get_logger

logger = get_logger("auth_client")

# Circuit breaker settings
FAILURE_THRESHOLD = 5
RECOVERY_TIMEOUT = 30  # seconds before trying again after circuit opens
REQUEST_TIMEOUT = 2.0  # seconds per HTTP request
MAX_RETRIES = 3
BACKOFF_BASE = 0.5  # seconds, multiplied by attempt number

# Circuit breaker state
_consecutive_failures = 0
_circuit_open_since: float | None = None


def _is_circuit_open() -> bool:
    """Check if the circuit breaker is open (auth service considered down)."""
    global _circuit_open_since
    if _circuit_open_since is None:
        return False
    elapsed = time.monotonic() - _circuit_open_since
    if elapsed >= RECOVERY_TIMEOUT:
        # Allow a probe request (half-open state)
        return False
    return True


def _record_success():
    """Record a successful call — close the circuit."""
    global _consecutive_failures, _circuit_open_since
    _consecutive_failures = 0
    _circuit_open_since = None


def _record_failure():
    """Record a failed call — open the circuit if threshold reached."""
    global _consecutive_failures, _circuit_open_since
    _consecutive_failures += 1
    if _consecutive_failures >= FAILURE_THRESHOLD:
        _circuit_open_since = time.monotonic()
        logger.warning(
            "circuit_breaker_opened",
            consecutive_failures=_consecutive_failures,
            recovery_timeout=RECOVERY_TIMEOUT,
        )


async def get_user_by_username(username: str) -> dict | None:
    """
    Look up a user by username via the Auth Service REST API.

    Returns a dict with at least {id, username} on success, or None if the user
    doesn't exist. Raises an exception if the auth service is unreachable after
    all retries (so the consumer can route to DLQ).

    Uses retry with exponential backoff + circuit breaker to avoid hammering
    a downed auth service.
    """
    if _is_circuit_open():
        raise ConnectionError(
            f"Auth service circuit breaker is open (>{FAILURE_THRESHOLD} consecutive failures)"
        )

    # Validate username to prevent path traversal / SSRF via crafted usernames
    # in Kafka messages. Only allow alphanumeric, underscore, hyphen, and dot.
    if not username or not re.match(r"^[a-zA-Z0-9_.\-]+$", username):
        logger.warning("invalid_username_rejected", username=username)
        return None

    # URL-encode the username to prevent path injection
    safe_username = quote(username, safe="")
    url = f"{AUTH_SERVICE_URL}/auth/users/by-username/{safe_username}"
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(url)

            if response.status_code == 200:
                _record_success()
                return response.json()
            elif response.status_code == 404:
                _record_success()
                return None
            else:
                last_error = f"Auth service returned {response.status_code}"
                logger.warning(
                    "auth_client_error",
                    url=url,
                    status=response.status_code,
                    attempt=attempt,
                )

        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
            last_error = str(e)
            logger.warning(
                "auth_client_timeout", url=url, attempt=attempt, error=str(e)
            )

        if attempt < MAX_RETRIES:
            await asyncio.sleep(BACKOFF_BASE * attempt)

    # All retries exhausted
    _record_failure()
    raise ConnectionError(
        f"Auth service unreachable after {MAX_RETRIES} attempts: {last_error}"
    )


def reset_circuit_breaker():
    """Reset the circuit breaker state. Used in tests."""
    global _consecutive_failures, _circuit_open_since
    _consecutive_failures = 0
    _circuit_open_since = None
