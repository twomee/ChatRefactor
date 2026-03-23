"""
End-to-end user journey load test.

Simulates the complete lifecycle a real user goes through:
  1. Register (unique username)
  2. Login (get JWT)
  3. List rooms
  4. Connect WebSocket to a room
  5. Send 3 chat messages
  6. Disconnect WebSocket
  7. Logout

This tests the full stack integration — auth, DB, Redis pub/sub, Kafka, WS.

Usage:
  locust -f scenarios/user_journey.py --host http://localhost \
    --headless --users 30 --spawn-rate 5 --run-time 5m
"""

import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path

import websocket as ws_sync  # websocket-client (synchronous)
from locust import HttpUser, between, events, task

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config

logger = logging.getLogger(__name__)


def _drain_ws(ws, expected_type: str, timeout: float = 5.0) -> dict | None:
    """Read WS messages until one of `expected_type` is found."""
    ws.settimeout(timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = ws.recv()
            data = json.loads(raw)
            if data.get("type") == expected_type:
                return data
        except (ws_sync.WebSocketTimeoutException, Exception):
            return None
    return None


class UserJourneyUser(HttpUser):
    """
    Full user lifecycle. Each iteration creates a unique user,
    goes through the complete flow, and cleans up.

    Think time: 2–5s (simulates human pacing).
    """

    wait_time = between(2, 5)
    host = config.api_base

    @task
    def full_journey(self):
        username = f"journey_{uuid.uuid4().hex[:8]}"
        password = "journey_pass_123"
        ws_conn = None

        try:
            # ── 1. Register ──
            with self.client.post(
                "/auth/register",
                json={"username": username, "password": password},
                name="journey: register",
                catch_response=True,
            ) as resp:
                if resp.status_code not in (200, 201):
                    resp.failure(f"Register failed: {resp.status_code}")
                    return

            # ── 2. Login ──
            with self.client.post(
                "/auth/login",
                json={"username": username, "password": password},
                name="journey: login",
                catch_response=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"Login failed: {resp.status_code}")
                    return
                token = resp.json()["access_token"]

            headers = {"Authorization": f"Bearer {token}"}

            # ── 3. List rooms ──
            with self.client.get(
                "/rooms",
                headers=headers,
                name="journey: list rooms",
                catch_response=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"List rooms failed: {resp.status_code}")
                    return
                rooms = resp.json()
                if not rooms:
                    resp.failure("No rooms available")
                    return
                room = random.choice(rooms)
                room_id = room["id"]

            # ── 4. Connect WebSocket ──
            ws_url = f"{config.ws_base}/ws/{room_id}?token={token}"
            start_ws = time.time()
            try:
                ws_conn = ws_sync.create_connection(ws_url, timeout=10)
                # Drain handshake messages
                _drain_ws(ws_conn, "history")
                _drain_ws(ws_conn, "user_join")

                ws_connect_time = (time.time() - start_ws) * 1000
                events.request.fire(
                    request_type="WS",
                    name="journey: ws_connect",
                    response_time=ws_connect_time,
                    response_length=0,
                    exception=None,
                    context=self.context(),
                )
            except Exception as e:
                ws_connect_time = (time.time() - start_ws) * 1000
                events.request.fire(
                    request_type="WS",
                    name="journey: ws_connect",
                    response_time=ws_connect_time,
                    response_length=0,
                    exception=e,
                    context=self.context(),
                )
                return

            # ── 5. Send messages ──
            for i in range(3):
                msg_text = f"journey_msg_{uuid.uuid4().hex[:6]}_{i}"
                payload = json.dumps({"type": "message", "text": msg_text})
                start_msg = time.time()

                try:
                    ws_conn.send(payload)

                    # Wait for echo broadcast
                    ws_conn.settimeout(10)
                    echo_found = False
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        raw = ws_conn.recv()
                        data = json.loads(raw)
                        if (
                            data.get("type") == "message"
                            and data.get("text") == msg_text
                        ):
                            echo_found = True
                            break

                    msg_time = (time.time() - start_msg) * 1000
                    events.request.fire(
                        request_type="WS",
                        name="journey: send_message",
                        response_time=msg_time,
                        response_length=len(payload),
                        exception=None if echo_found else Exception("No echo"),
                        context=self.context(),
                    )
                except Exception as e:
                    msg_time = (time.time() - start_msg) * 1000
                    events.request.fire(
                        request_type="WS",
                        name="journey: send_message",
                        response_time=msg_time,
                        response_length=0,
                        exception=e,
                        context=self.context(),
                    )

                # Human-like pause between messages
                time.sleep(random.uniform(0.5, 1.5))

            # ── 6. Disconnect WebSocket ──
            ws_conn.close()
            ws_conn = None

            # ── 7. Logout ──
            self.client.post(
                "/auth/logout",
                headers=headers,
                name="journey: logout",
            )

        finally:
            if ws_conn:
                try:
                    ws_conn.close()
                except Exception:
                    pass
