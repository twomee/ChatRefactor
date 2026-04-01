"""
Shared fixtures for the Chat-Project e2e test suite.

All API calls go through the Kong gateway. The fixtures auto-detect
the gateway URL, resolve admin credentials from multiple sources,
and provision throwaway users/rooms scoped to the entire test session.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Helpers (non-fixture)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_kong_url() -> str:
    """Return the Kong gateway base URL.

    Resolution order:
      1. KONG_URL environment variable
      2. localhost:80   (Docker Compose)
      3. localhost:30080 (K8s NodePort)
    """
    env_url = os.environ.get("KONG_URL")
    if env_url:
        return env_url.rstrip("/")

    for port in (80, 8090, 30080, 31080):
        url = f"http://localhost:{port}"
        try:
            resp = requests.get(url, timeout=3)
            # Any response (even 404) means the gateway is up.
            if resp.status_code < 600:
                return url
        except requests.ConnectionError:
            continue

    pytest.exit(
        "Could not reach Kong gateway.\n"
        "Tried: KONG_URL env var, localhost:80, localhost:8090, localhost:30080, localhost:31080.\n"
        "Make sure Docker Compose or K8s is running and Kong is accessible.",
        returncode=1,
    )


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file, ignoring comments and blanks."""
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if match:
            env[match.group(1)] = match.group(2)
    return env


def _resolve_admin_creds() -> tuple[str, str]:
    """Return (username, password) for the admin account.

    Resolution order:
      1. ADMIN_USER or ADMIN_USERNAME + ADMIN_PASSWORD env vars
      2. Root .env file
      3. infra/k8s/secrets.env
      4. kubectl get secret
      5. Defaults: admin / changeme
    """
    # --- 1. Env vars ---
    username = os.environ.get("ADMIN_USER") or os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if username and password:
        return username, password

    # --- 2. Root .env ---
    root_env = _parse_env_file(_PROJECT_ROOT / ".env")
    username = root_env.get("ADMIN_USER") or root_env.get("ADMIN_USERNAME")
    password = root_env.get("ADMIN_PASSWORD")
    if username and password:
        return username, password

    # --- 3. K8s secrets.env ---
    k8s_env = _parse_env_file(_PROJECT_ROOT / "infra" / "k8s" / "secrets.env")
    username = k8s_env.get("ADMIN_USER") or k8s_env.get("ADMIN_USERNAME")
    password = k8s_env.get("ADMIN_PASSWORD")
    if username and password:
        return username, password

    # --- 4. kubectl ---
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "secret",
                "auth-admin-secret",
                "-n",
                "chatbox",
                "-o",
                "jsonpath={.data.ADMIN_USERNAME}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            import base64

            kb_user = base64.b64decode(result.stdout).decode()
            result2 = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "secret",
                    "auth-admin-secret",
                    "-n",
                    "chatbox",
                    "-o",
                    "jsonpath={.data.ADMIN_PASSWORD}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result2.returncode == 0 and result2.stdout:
                kb_pass = base64.b64decode(result2.stdout).decode()
                return kb_user, kb_pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # --- 5. Defaults ---
    return "admin", "changeme"


def auth_header(token: str) -> dict[str, str]:
    """Return an Authorization header dict for the given bearer token."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def kong_url() -> str:
    """Resolved Kong gateway base URL (e.g. http://localhost)."""
    return _resolve_kong_url()


@pytest.fixture(scope="session")
def ws_url(kong_url: str) -> str:
    """WebSocket URL derived from the Kong base URL (http -> ws)."""
    return kong_url.replace("http://", "ws://").replace("https://", "wss://")


@pytest.fixture(scope="session")
def api() -> requests.Session:
    """A shared requests.Session.

    Do NOT set a default Content-Type header here — it corrupts multipart
    file uploads.  The json= kwarg sets application/json automatically,
    and files= sets multipart/form-data automatically.
    """
    return requests.Session()


@pytest.fixture(scope="session")
def timestamp() -> str:
    """Unique timestamp string for test isolation."""
    return str(int(time.time()))


@pytest.fixture(scope="session")
def admin_creds() -> tuple[str, str]:
    """Admin (username, password) tuple."""
    return _resolve_admin_creds()


@pytest.fixture(scope="session")
def _admin_login_data(kong_url: str, api: requests.Session, admin_creds: tuple[str, str]) -> dict:
    """Full admin login response data."""
    username, password = admin_creds
    resp = api.post(
        f"{kong_url}/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Admin login failed ({resp.status_code}): {resp.text}"
    return resp.json()


@pytest.fixture(scope="session")
def admin_token(_admin_login_data: dict) -> str:
    """JWT obtained by logging in as the admin user."""
    return _admin_login_data["access_token"]


@pytest.fixture(scope="session")
def admin_user_id(_admin_login_data: dict) -> int:
    """User ID of the admin."""
    return _admin_login_data["user_id"]


def _register_and_login(
    kong_url: str,
    api: requests.Session,
    username: str,
    password: str,
    email: str,
) -> dict:
    """Register a new user and log them in, returning user info dict."""
    # Register
    reg_resp = api.post(
        f"{kong_url}/auth/register",
        json={"username": username, "password": password, "email": email},
    )
    assert reg_resp.status_code in (
        200,
        201,
    ), f"Register {username} failed ({reg_resp.status_code}): {reg_resp.text}"

    # Login
    login_resp = api.post(
        f"{kong_url}/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200, (
        f"Login {username} failed ({login_resp.status_code}): {login_resp.text}"
    )
    data = login_resp.json()

    return {
        "username": username,
        "password": password,
        "email": email,
        "token": data["access_token"],
        "user_id": data["user_id"],
    }


@pytest.fixture(scope="session")
def user1(kong_url: str, api: requests.Session, timestamp: str) -> dict:
    """Test user alice_<ts> — registered and logged in."""
    return _register_and_login(
        kong_url,
        api,
        username=f"alice_{timestamp}",
        password="TestPass123!",
        email=f"alice_{timestamp}@test.com",
    )


@pytest.fixture(scope="session")
def user2(kong_url: str, api: requests.Session, timestamp: str) -> dict:
    """Test user bob_<ts> — registered and logged in."""
    return _register_and_login(
        kong_url,
        api,
        username=f"bob_{timestamp}",
        password="TestPass123!",
        email=f"bob_{timestamp}@test.com",
    )


@pytest.fixture(scope="session")
def user3(kong_url: str, api: requests.Session, timestamp: str) -> dict:
    """Test user charlie_<ts> — registered and logged in (for admin/kick/mute tests)."""
    return _register_and_login(
        kong_url,
        api,
        username=f"charlie_{timestamp}",
        password="TestPass123!",
        email=f"charlie_{timestamp}@test.com",
    )


@pytest.fixture(scope="session")
def user4(kong_url: str, api: requests.Session, timestamp: str) -> dict:
    """Test user for 2FA tests — registered and logged in."""
    return _register_and_login(
        kong_url,
        api,
        username=f"delta_{timestamp}",
        password="TestPass123!",
        email=f"delta_{timestamp}@test.com",
    )


@pytest.fixture(scope="session")
def user5(kong_url: str, api: requests.Session, timestamp: str) -> dict:
    """Test user for password change / logout tests — registered and logged in."""
    return _register_and_login(
        kong_url,
        api,
        username=f"echo_{timestamp}",
        password="TestPass123!",
        email=f"echo_{timestamp}@test.com",
    )


@pytest.fixture(scope="session")
def test_room(
    kong_url: str,
    api: requests.Session,
    admin_token: str,
    timestamp: str,
) -> dict:
    """Admin-created room for testing. Returns {id, name}."""
    resp = api.post(
        f"{kong_url}/rooms",
        json={"name": f"testroom_{timestamp}"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code in (200, 201), (
        f"Create room failed ({resp.status_code}): {resp.text}"
    )
    data = resp.json()
    return {"id": data["id"], "name": data["name"]}


@pytest.fixture(scope="session")
def default_rooms(kong_url: str, api: requests.Session, admin_token: str) -> list:
    """List of room objects from GET /rooms."""
    resp = api.get(
        f"{kong_url}/rooms",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200, f"GET /rooms failed ({resp.status_code}): {resp.text}"
    return resp.json()
