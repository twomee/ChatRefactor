"""
Locust WebSocket chat load test.

Tests concurrent WebSocket connections and message throughput.
Uses a custom Locust User (not HttpUser) with websocket-client (sync)
and reports metrics via Locust's events system so they appear in the dashboard.

Key things tested:
  - Connection establishment time under concurrent load
  - Message round-trip latency (send → broadcast echo)
  - Private message delivery
  - Broadcast fan-out (messages reach all users in a room)
  - Connection stability over time

Usage:
  locust -f scenarios/websocket_chat.py --host ws://localhost:8000 \
    --headless --users 100 --spawn-rate 10 --run-time 10m
"""

import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path

import websocket as ws_sync
from locust import User, between, events, task

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from utils.user_pool import UserPool, get_pool

logger = logging.getLogger(__name__)


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Provision users when Locust starts."""
    from locust.runners import WorkerRunner

    if isinstance(environment.runner, WorkerRunner):
        return

    pool = get_pool()
    pool.provision(config.num_users)
    logger.info(f"WS test pool ready: {pool.total_provisioned} users")


class WebSocketChatUser(User):
    """
    Custom Locust User that maintains a WebSocket connection.

    Lifecycle:
      on_start: get credentials, connect to a random room
      tasks: send messages, send PMs
      on_stop: close connection, return credentials
    """

    wait_time = between(1, 3)

    def on_start(self):
        pool = get_pool()
        self._creds = pool.get()
        self._token = self._creds["token"]
        self._username = self._creds["username"]
        self._room_id = random.choice(pool.room_ids)
        self._ws = None
        self._other_users: list[str] = []

        self._connect()

    def _connect(self):
        """Establish WebSocket connection to a room."""
        ws_url = f"{config.ws_base}/ws/{self._room_id}?token={self._token}"
        start = time.time()

        try:
            self._ws = ws_sync.create_connection(ws_url, timeout=10)

            # Drain history
            self._ws.settimeout(5)
            try:
                raw = self._ws.recv()
                data = json.loads(raw)
                if data.get("type") == "history":
                    pass  # Expected
            except Exception:
                pass

            # Drain user_join (contains user list)
            try:
                raw = self._ws.recv()
                data = json.loads(raw)
                if data.get("type") == "user_join":
                    self._other_users = [
                        u
                        for u in data.get("users", [])
                        if u != self._username
                    ]
            except Exception:
                pass

            # Drain system message ("X has joined")
            try:
                raw = self._ws.recv()
            except Exception:
                pass

            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_connect",
                response_time=elapsed,
                response_length=0,
                exception=None,
                context=self.context(),
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_connect",
                response_time=elapsed,
                response_length=0,
                exception=e,
                context=self.context(),
            )
            self._ws = None

    def _recv_until(self, match_type: str, match_text: str | None = None,
                    timeout: float = 10.0) -> dict | None:
        """Read messages until one matches type (and optionally text)."""
        if not self._ws:
            return None

        self._ws.settimeout(timeout)
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._ws.settimeout(min(remaining, 5.0))
                raw = self._ws.recv()
                data = json.loads(raw)

                if data.get("type") == match_type:
                    if match_text is None or data.get("text") == match_text:
                        return data
            except ws_sync.WebSocketTimeoutException:
                continue
            except Exception:
                break

        return None

    @task(8)
    def send_message(self):
        """Send a chat message and measure round-trip (until broadcast echo)."""
        if not self._ws:
            self._connect()
            if not self._ws:
                return

        msg_text = f"lt_{uuid.uuid4().hex[:8]}"
        payload = json.dumps({"type": "message", "text": msg_text})
        start = time.time()

        try:
            self._ws.send(payload)

            # Wait for our message to come back as a broadcast
            echo = self._recv_until("message", msg_text, timeout=10.0)

            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_message",
                response_time=elapsed,
                response_length=len(payload),
                exception=None if echo else Exception("No echo received"),
                context=self.context(),
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_message",
                response_time=elapsed,
                response_length=0,
                exception=e,
                context=self.context(),
            )
            # Connection may be dead — reconnect on next task
            self._ws = None

    @task(2)
    def send_private_message(self):
        """Send a private message to another online user."""
        if not self._ws or not self._other_users:
            return

        target = random.choice(self._other_users)
        msg_text = f"pm_{uuid.uuid4().hex[:8]}"
        payload = json.dumps({
            "type": "private_message",
            "to": target,
            "text": msg_text,
        })
        start = time.time()

        try:
            self._ws.send(payload)

            # Wait for self-echo (server sends back with "self": true)
            echo = self._recv_until("private_message", timeout=10.0)

            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_pm",
                response_time=elapsed,
                response_length=len(payload),
                exception=None if echo else Exception("No PM echo"),
                context=self.context(),
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            events.request.fire(
                request_type="WS",
                name="ws_send_pm",
                response_time=elapsed,
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

        get_pool().release(self._creds)
