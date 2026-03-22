"""
Microservices load test suite for cHATBOX.

Tests all four microservices through the Kong API Gateway:
  - AuthUser: registration, login, token refresh, logout
  - ChatUser: WebSocket connections, real-time messaging
  - FileUser: file upload and download throughput
  - MessageUser: message history and replay API

Usage:
  # All user classes (default weights)
  locust -f locustfile.py --host http://localhost

  # Single user class
  locust -f locustfile.py AuthUser --host http://localhost

  # Headless CI mode
  locust -f locustfile.py --headless \
    --users 200 --spawn-rate 20 --run-time 10m \
    --host http://localhost \
    --csv reports/microservices --html reports/microservices.html
"""

import json
import logging
import os
import random
import string
import time
import uuid

import websocket as ws_sync
from locust import HttpUser, User, between, events, task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Kong gateway URL — override via --host flag or environment variable
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost")
WS_GATEWAY_URL = os.getenv("WS_GATEWAY_URL", "ws://localhost")

# Shared credentials for pre-authenticated flows
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ido")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Prefix for dynamically created load test users
USER_PREFIX = os.getenv("LOADTEST_USER_PREFIX", "lt_user")
USER_PASSWORD = os.getenv("LOADTEST_USER_PASSWORD", "LoadTest_Pass_123!")


def _random_suffix(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ---------------------------------------------------------------------------
# Shared token cache (avoid re-login on every user spawn)
# ---------------------------------------------------------------------------

_token_cache: dict[str, str] = {}


def _login(client, username: str, password: str) -> str | None:
    """Authenticate via auth-service through Kong and return a JWT token."""
    if username in _token_cache:
        return _token_cache[username]

    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        name="/api/auth/login",
    )
    if resp.status_code == 200:
        token = resp.json().get("access_token")
        if token:
            _token_cache[username] = token
            return token
    return None


def _register_and_login(client) -> tuple[str, str, str] | None:
    """Register a new user and return (username, password, token)."""
    username = f"{USER_PREFIX}_{_random_suffix()}"
    password = USER_PASSWORD

    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
        name="/api/auth/register",
    )
    if resp.status_code not in (200, 201, 409):
        return None

    token = _login(client, username, password)
    if token:
        return username, password, token
    return None


# ---------------------------------------------------------------------------
# AuthUser — tests auth-service (Python, port 8001)
# ---------------------------------------------------------------------------


class AuthUser(HttpUser):
    """
    Simulates authentication workloads through Kong -> auth-service.

    Tasks:
      - Register new accounts (weight 1)
      - Login with existing credentials (weight 5)
      - Validate current token (weight 3)
      - Logout and invalidate token (weight 1)

    Tests registration throughput, JWT issuance, token validation,
    and Redis-backed token blacklisting.
    """

    wait_time = between(1, 3)
    weight = 3

    def on_start(self):
        """Register a unique user and obtain a JWT token."""
        result = _register_and_login(self.client)
        if result:
            self._username, self._password, self._token = result
            self._headers = {"Authorization": f"Bearer {self._token}"}
        else:
            self._username = None
            self._password = None
            self._token = None
            self._headers = {}

    @task(5)
    def login(self):
        """POST /api/auth/login — measure JWT issuance latency."""
        if not self._username:
            return
        resp = self.client.post(
            "/api/auth/login",
            json={"username": self._username, "password": self._password},
            name="/api/auth/login",
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                self._token = token
                self._headers = {"Authorization": f"Bearer {self._token}"}

    @task(1)
    def register(self):
        """POST /api/auth/register — measure registration throughput."""
        username = f"{USER_PREFIX}_{_random_suffix()}"
        self.client.post(
            "/api/auth/register",
            json={"username": username, "password": USER_PASSWORD},
            name="/api/auth/register",
        )

    @task(3)
    def validate_token(self):
        """GET /api/auth/me — validate JWT and return user info."""
        if not self._token:
            return
        self.client.get(
            "/api/auth/me",
            headers=self._headers,
            name="/api/auth/me",
        )

    @task(1)
    def logout_and_relogin(self):
        """POST /api/auth/logout then re-login — tests token blacklisting."""
        if not self._token:
            return
        self.client.post(
            "/api/auth/logout",
            headers=self._headers,
            name="/api/auth/logout",
        )
        # Re-login to get a fresh token
        self.login()


# ---------------------------------------------------------------------------
# ChatUser — tests chat-service (Go, port 8003)
# ---------------------------------------------------------------------------


class ChatUser(User):
    """
    Simulates real-time chat via WebSocket through Kong -> chat-service.

    Lifecycle:
      on_start: authenticate, open WebSocket to a room
      tasks: send messages, send PMs
      on_stop: close connection

    Tests WebSocket connection establishment, message round-trip latency,
    broadcast fan-out, and connection stability under load.
    """

    wait_time = between(1, 3)
    weight = 5

    # Room IDs to connect to (1-3 are defaults: politics, sports, movies)
    ROOM_IDS = [1, 2, 3]

    def on_start(self):
        """Authenticate via REST, then open a WebSocket connection."""
        self._ws = None
        self._token = None
        self._username = None

        # Register and login via HTTP to get a token
        import requests

        base = os.getenv("GATEWAY_URL", self.host or "http://localhost")
        username = f"{USER_PREFIX}_{_random_suffix()}"
        password = USER_PASSWORD

        try:
            # Register
            requests.post(
                f"{base}/api/auth/register",
                json={"username": username, "password": password},
                timeout=10,
            )
            # Login
            resp = requests.post(
                f"{base}/api/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
                self._username = username
        except Exception as e:
            logger.warning(f"ChatUser auth failed: {e}")
            return

        if self._token:
            self._room_id = random.choice(self.ROOM_IDS)
            self._connect()

    def _connect(self):
        """Establish WebSocket connection to a chat room via Kong."""
        ws_base = os.getenv(
            "WS_GATEWAY_URL",
            (self.host or "http://localhost").replace("http", "ws"),
        )
        ws_url = f"{ws_base}/ws/chat/{self._room_id}?token={self._token}"
        start = time.time()

        try:
            self._ws = ws_sync.create_connection(ws_url, timeout=10)

            # Drain initial messages (history, user_join, system)
            self._ws.settimeout(3)
            for _ in range(5):
                try:
                    self._ws.recv()
                except Exception:
                    break

            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_connect",
                response_time=elapsed_ms,
                response_length=0,
                exception=None,
                context=self.context(),
            )
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_connect",
                response_time=elapsed_ms,
                response_length=0,
                exception=e,
                context=self.context(),
            )
            self._ws = None

    @task(8)
    def send_message(self):
        """Send a chat message and measure round-trip time."""
        if not self._ws:
            self._connect()
            if not self._ws:
                return

        msg_text = f"lt_{uuid.uuid4().hex[:8]}"
        payload = json.dumps({"type": "message", "text": msg_text})
        start = time.time()

        try:
            self._ws.send(payload)

            # Wait for broadcast echo
            self._ws.settimeout(10)
            echo_received = False
            deadline = time.monotonic() + 10

            while time.monotonic() < deadline:
                try:
                    raw = self._ws.recv()
                    data = json.loads(raw)
                    if data.get("type") == "message" and data.get("text") == msg_text:
                        echo_received = True
                        break
                except ws_sync.WebSocketTimeoutException:
                    break
                except Exception:
                    break

            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_message",
                response_time=elapsed_ms,
                response_length=len(payload),
                exception=None if echo_received else Exception("No echo received"),
                context=self.context(),
            )
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_message",
                response_time=elapsed_ms,
                response_length=0,
                exception=e,
                context=self.context(),
            )
            self._ws = None

    @task(2)
    def send_private_message(self):
        """Send a private message to a random user handle."""
        if not self._ws:
            return

        target = f"{USER_PREFIX}_{_random_suffix()}"
        msg_text = f"pm_{uuid.uuid4().hex[:8]}"
        payload = json.dumps({
            "type": "private_message",
            "to": target,
            "text": msg_text,
        })
        start = time.time()

        try:
            self._ws.send(payload)

            # Wait for server acknowledgement
            self._ws.settimeout(5)
            try:
                self._ws.recv()
            except Exception:
                pass

            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_pm",
                response_time=elapsed_ms,
                response_length=len(payload),
                exception=None,
                context=self.context(),
            )
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_pm",
                response_time=elapsed_ms,
                response_length=0,
                exception=e,
                context=self.context(),
            )
            self._ws = None

    def on_stop(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# FileUser — tests file-service (Node.js/TypeScript, port 8005)
# ---------------------------------------------------------------------------


class FileUser(HttpUser):
    """
    Simulates file upload and download workloads through Kong -> file-service.

    Tasks:
      - Upload small text files (weight 3)
      - Upload medium binary files (weight 1)
      - List files in a room (weight 4)
      - Download a previously uploaded file (weight 2)

    Tests multipart upload handling, disk I/O throughput, and
    Kafka event emission for file metadata.
    """

    wait_time = between(1, 3)
    weight = 2

    def on_start(self):
        """Register, login, and prepare file data."""
        result = _register_and_login(self.client)
        if result:
            self._username, self._password, self._token = result
            self._headers = {"Authorization": f"Bearer {self._token}"}
        else:
            self._username = None
            self._token = None
            self._headers = {}

        self._uploaded_file_ids: list[str] = []
        self._room_id = random.choice([1, 2, 3])

        # Pre-generate file content to avoid repeated allocation
        self._small_file = b"Load test file content. " * 100  # ~2.4 KB
        self._medium_file = os.urandom(1024 * 512)  # 512 KB

    @task(3)
    def upload_small_file(self):
        """POST /api/files/upload — upload a small text file."""
        if not self._token:
            return

        filename = f"lt_small_{_random_suffix()}.txt"
        resp = self.client.post(
            "/api/files/upload",
            headers=self._headers,
            files={"file": (filename, self._small_file, "text/plain")},
            data={"room_id": str(self._room_id)},
            name="/api/files/upload (small)",
        )
        if resp.status_code in (200, 201):
            file_id = resp.json().get("id") or resp.json().get("file_id")
            if file_id:
                self._uploaded_file_ids.append(str(file_id))

    @task(1)
    def upload_medium_file(self):
        """POST /api/files/upload — upload a 512KB binary file."""
        if not self._token:
            return

        filename = f"lt_medium_{_random_suffix()}.bin"
        resp = self.client.post(
            "/api/files/upload",
            headers=self._headers,
            files={"file": (filename, self._medium_file, "application/octet-stream")},
            data={"room_id": str(self._room_id)},
            name="/api/files/upload (medium)",
        )
        if resp.status_code in (200, 201):
            file_id = resp.json().get("id") or resp.json().get("file_id")
            if file_id:
                self._uploaded_file_ids.append(str(file_id))

    @task(4)
    def list_files(self):
        """GET /api/files/ — list files in a room."""
        if not self._token:
            return
        self.client.get(
            f"/api/files/?room_id={self._room_id}",
            headers=self._headers,
            name="/api/files/ (list)",
        )

    @task(2)
    def download_file(self):
        """GET /api/files/{id}/download — download a previously uploaded file."""
        if not self._token or not self._uploaded_file_ids:
            return

        file_id = random.choice(self._uploaded_file_ids)
        self.client.get(
            f"/api/files/{file_id}/download",
            headers=self._headers,
            name="/api/files/[id]/download",
        )


# ---------------------------------------------------------------------------
# MessageUser — tests message-service (Python, port 8004)
# ---------------------------------------------------------------------------


class MessageUser(HttpUser):
    """
    Simulates message history and replay API through Kong -> message-service.

    Tasks:
      - Get message history for a room (weight 5)
      - Get messages since a timestamp (weight 3)
      - Get messages with pagination (weight 2)
      - Health check (weight 1)

    Tests query performance under concurrent load, pagination handling,
    and database read throughput for the message store.
    """

    wait_time = between(1, 3)
    weight = 4

    def on_start(self):
        """Authenticate to access message history endpoints."""
        result = _register_and_login(self.client)
        if result:
            self._username, self._password, self._token = result
            self._headers = {"Authorization": f"Bearer {self._token}"}
        else:
            self._username = None
            self._token = None
            self._headers = {}

        self._room_ids = [1, 2, 3]

    @task(5)
    def get_room_messages(self):
        """GET /api/messages/rooms/{id} — fetch recent message history."""
        if not self._token:
            return

        room_id = random.choice(self._room_ids)
        self.client.get(
            f"/api/messages/rooms/{room_id}?limit=50",
            headers=self._headers,
            name="/api/messages/rooms/[id]",
        )

    @task(3)
    def get_messages_since(self):
        """GET /api/messages/rooms/{id}?since=... — message replay from timestamp."""
        if not self._token:
            return

        room_id = random.choice(self._room_ids)
        # Request messages from the last hour
        since_ts = int(time.time()) - 3600
        self.client.get(
            f"/api/messages/rooms/{room_id}?since={since_ts}&limit=100",
            headers=self._headers,
            name="/api/messages/rooms/[id]?since=",
        )

    @task(2)
    def get_messages_paginated(self):
        """GET /api/messages/rooms/{id}?offset=...&limit=... — paginated history."""
        if not self._token:
            return

        room_id = random.choice(self._room_ids)
        offset = random.randint(0, 200)
        self.client.get(
            f"/api/messages/rooms/{room_id}?offset={offset}&limit=20",
            headers=self._headers,
            name="/api/messages/rooms/[id]?paginated",
        )

    @task(1)
    def get_private_messages(self):
        """GET /api/messages/private — fetch private message history."""
        if not self._token:
            return
        self.client.get(
            "/api/messages/private?limit=20",
            headers=self._headers,
            name="/api/messages/private",
        )

    @task(1)
    def health_check(self):
        """GET /api/messages/health — message-service health probe."""
        self.client.get(
            "/api/messages/health",
            name="/api/messages/health",
        )
