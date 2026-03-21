"""
Async WebSocket client for load testing.

Handles the full cHATBOX WebSocket lifecycle:
  1. Connect with JWT token as query param
  2. Drain initial messages (history, user_join, system)
  3. Send/receive messages with round-trip timing
  4. Graceful disconnect

Used by:
  - scripts/ws_stress.py (standalone asyncio stress test)
  - Can be adapted for Locust custom User classes
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import websockets

logger = logging.getLogger(__name__)


@dataclass
class WSMetrics:
    """Metrics collected during a WebSocket session."""

    connect_time_ms: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    round_trips: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    connected: bool = False
    disconnected_unexpectedly: bool = False

    @property
    def avg_round_trip_ms(self) -> float:
        return sum(self.round_trips) / len(self.round_trips) if self.round_trips else 0

    @property
    def p50_ms(self) -> float:
        return self._percentile(50)

    @property
    def p95_ms(self) -> float:
        return self._percentile(95)

    @property
    def p99_ms(self) -> float:
        return self._percentile(99)

    def _percentile(self, p: int) -> float:
        if not self.round_trips:
            return 0.0
        sorted_rt = sorted(self.round_trips)
        idx = int(len(sorted_rt) * p / 100)
        return sorted_rt[min(idx, len(sorted_rt) - 1)]

    def to_dict(self) -> dict:
        return {
            "connect_time_ms": round(self.connect_time_ms, 2),
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "avg_round_trip_ms": round(self.avg_round_trip_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "errors": self.errors,
            "connected": self.connected,
            "disconnected_unexpectedly": self.disconnected_unexpectedly,
        }


class AsyncWSClient:
    """Async WebSocket client that matches the cHATBOX protocol."""

    def __init__(self, ws_base: str, token: str, room_id: int):
        self.url = f"{ws_base}/ws/{room_id}?token={token}"
        self.room_id = room_id
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.metrics = WSMetrics()
        self._pending_echoes: dict[str, float] = {}  # msg_text -> send_time

    async def connect(self, timeout: float = 10.0) -> float:
        """
        Connect and drain initial handshake messages.
        Returns connection time in milliseconds.
        """
        start = time.monotonic()
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**20,  # 1MB max message
                ),
                timeout=timeout,
            )

            # Drain initial messages: history, user_join, system
            for _ in range(5):
                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    data = json.loads(raw)
                    msg_type = data.get("type", "")
                    if msg_type in ("history", "user_join", "system"):
                        self.metrics.messages_received += 1
                        continue
                    # Got an unexpected message type — stop draining
                    break
                except asyncio.TimeoutError:
                    break

            elapsed_ms = (time.monotonic() - start) * 1000
            self.metrics.connect_time_ms = elapsed_ms
            self.metrics.connected = True
            return elapsed_ms

        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            self.metrics.connect_time_ms = elapsed_ms
            self.metrics.errors.append(f"connect: {e}")
            raise

    async def send_message(self, text: str) -> None:
        """Send a chat message. Track send time for round-trip measurement."""
        if not self.ws:
            raise RuntimeError("Not connected")

        payload = json.dumps({"type": "message", "text": text})
        self._pending_echoes[text] = time.monotonic()
        await self.ws.send(payload)
        self.metrics.messages_sent += 1

    async def send_and_wait_echo(self, text: str, timeout: float = 10.0) -> float:
        """
        Send a message and wait for it to be broadcast back.
        Returns round-trip time in milliseconds.
        """
        if not self.ws:
            raise RuntimeError("Not connected")

        payload = json.dumps({"type": "message", "text": text})
        start = time.monotonic()
        await self.ws.send(payload)
        self.metrics.messages_sent += 1

        # Wait for the echo (server broadcasts to all including sender)
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            data = json.loads(raw)
            self.metrics.messages_received += 1

            if data.get("type") == "message" and data.get("text") == text:
                elapsed_ms = (time.monotonic() - start) * 1000
                self.metrics.round_trips.append(elapsed_ms)
                return elapsed_ms

    async def receive_loop(self, duration: float) -> None:
        """
        Receive messages for `duration` seconds.
        Completes round-trip measurements for pending echoes.
        """
        if not self.ws:
            return

        end_time = time.monotonic() + duration
        try:
            while time.monotonic() < end_time:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(
                        self.ws.recv(), timeout=min(remaining, 5.0)
                    )
                    data = json.loads(raw)
                    self.metrics.messages_received += 1

                    # Check if this completes a round-trip measurement
                    if data.get("type") == "message":
                        text = data.get("text", "")
                        if text in self._pending_echoes:
                            send_time = self._pending_echoes.pop(text)
                            elapsed_ms = (time.monotonic() - send_time) * 1000
                            self.metrics.round_trips.append(elapsed_ms)

                except asyncio.TimeoutError:
                    continue
        except websockets.ConnectionClosed:
            self.metrics.disconnected_unexpectedly = True

    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
            self.metrics.connected = False
