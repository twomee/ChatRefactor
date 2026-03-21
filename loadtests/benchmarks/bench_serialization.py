"""
Micro-benchmarks for JSON serialization (WebSocket message encoding).

Every WebSocket message goes through json.dumps (send) and json.loads (receive).
At high message throughput, serialization overhead adds up.

Usage:
  cd loadtests
  pytest benchmarks/bench_serialization.py --benchmark-only -v
"""

import json
import uuid
from datetime import datetime, timezone

import pytest


# ── Typical message payloads ──

CHAT_MESSAGE = {
    "type": "message",
    "from": "loadtest_user_0042",
    "text": "Hello, this is a load test message with some content!",
    "room_id": 3,
    "msg_id": str(uuid.uuid4()),
    "timestamp": datetime.now(timezone.utc).isoformat(),
}

HISTORY_MESSAGE = {
    "type": "history",
    "messages": [
        {
            "from": f"user_{i}",
            "text": f"Historical message number {i} with some content",
            "msg_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(50)
    ],
    "room_id": 3,
}

USER_JOIN_MESSAGE = {
    "type": "user_join",
    "username": "loadtest_user_0042",
    "users": [f"user_{i}" for i in range(30)],
    "admins": ["user_0"],
    "muted": ["user_5", "user_12"],
    "room_id": 3,
}

PRIVATE_MESSAGE = {
    "type": "private_message",
    "from": "user_a",
    "to": "user_b",
    "text": "Private message content here",
    "msg_id": str(uuid.uuid4()),
}


# ── Encode benchmarks ──


def test_encode_chat_message(benchmark):
    """json.dumps for a typical chat message."""
    benchmark(json.dumps, CHAT_MESSAGE)


def test_encode_history(benchmark):
    """json.dumps for history payload (50 messages — sent on connect)."""
    benchmark(json.dumps, HISTORY_MESSAGE)


def test_encode_user_join(benchmark):
    """json.dumps for user_join (30 users — sent on connect)."""
    benchmark(json.dumps, USER_JOIN_MESSAGE)


# ── Decode benchmarks ──


def test_decode_chat_message(benchmark):
    """json.loads for a typical chat message."""
    encoded = json.dumps(CHAT_MESSAGE)
    benchmark(json.loads, encoded)


def test_decode_history(benchmark):
    """json.loads for history payload."""
    encoded = json.dumps(HISTORY_MESSAGE)
    benchmark(json.loads, encoded)


def test_decode_user_join(benchmark):
    """json.loads for user_join."""
    encoded = json.dumps(USER_JOIN_MESSAGE)
    benchmark(json.loads, encoded)


# ── Round-trip (encode + decode) ──


def test_roundtrip_chat_message(benchmark):
    """Full encode → decode cycle for a chat message."""

    def roundtrip():
        encoded = json.dumps(CHAT_MESSAGE)
        json.loads(encoded)

    benchmark(roundtrip)


def test_roundtrip_history(benchmark):
    """Full encode → decode cycle for history (heaviest payload)."""

    def roundtrip():
        encoded = json.dumps(HISTORY_MESSAGE)
        json.loads(encoded)

    benchmark(roundtrip)
