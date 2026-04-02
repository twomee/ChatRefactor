"""Shared helper functions for the e2e test suite.

These are plain functions (not fixtures) that test modules import directly.
Fixtures live in conftest.py and are auto-discovered by pytest.
"""

from __future__ import annotations

import asyncio
import json
import time

import websockets


def auth_header(token: str) -> dict[str, str]:
    """Return an Authorization header dict for the given bearer token."""
    return {"Authorization": f"Bearer {token}"}


async def ws_connect(ws_url: str, path: str, token: str, silent: bool = False):
    """Connect to a WebSocket endpoint. Returns the connection."""
    url = f"{ws_url}{path}?token={token}"
    if silent:
        url += "&silent=1"
    return await websockets.connect(url, ping_interval=None, open_timeout=10)


async def recv_until(ws, msg_type: str, timeout: float = 5.0):
    """Receive messages until one matches the given type, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = deadline - time.time()
            raw = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
            data = json.loads(raw)
            if data.get("type") == msg_type:
                return data
        except asyncio.TimeoutError:
            break
    return None


async def drain(ws, timeout: float = 0.5):
    """Drain all pending messages from a WebSocket."""
    messages = []
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            messages.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
    return messages
