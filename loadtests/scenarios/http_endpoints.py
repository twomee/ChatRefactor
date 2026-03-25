"""
Locust HTTP endpoint load test.

Tests REST API throughput and latency under concurrent load.
All requests go through Kong (port 80) which routes to the correct microservice.
Weighted tasks simulate realistic traffic distribution:
  - list_rooms: most frequent (users check room list often)
  - get_room_users: moderate (checking who's online)
  - get_messages: moderate (message replay/history)
  - list_files: low (file browser)

Usage:
  # With Locust web UI
  locust -f scenarios/http_endpoints.py --host http://localhost

  # Headless (CI mode)
  locust -f scenarios/http_endpoints.py --headless \
    --users 100 --spawn-rate 10 --run-time 10m \
    --host http://localhost \
    --csv reports/http_load --html reports/http_load.html
"""

import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from locust import HttpUser, between, events, task

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from utils.user_pool import UserPool, get_pool

logger = logging.getLogger(__name__)

# ─── Setup: provision users once before any Locust workers spawn ────────────

_pool: UserPool | None = None


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Provision users when Locust master starts (or in standalone mode)."""
    global _pool

    # Only provision on master (or standalone — runner_class won't be WorkerRunner)
    from locust.runners import WorkerRunner

    if isinstance(environment.runner, WorkerRunner):
        return

    logger.info("Provisioning load test users ...")
    _pool = get_pool()
    _pool.provision(config.num_users)
    logger.info(
        f"User pool ready: {_pool.total_provisioned} users, "
        f"rooms: {_pool.room_ids}"
    )


# ─── HTTP Load Test User ───────────────────────────────────────────────────


class ChatHttpUser(HttpUser):
    """
    Simulates an authenticated user making REST API calls.

    Think time: 0.5–2s between requests (simulates human browsing).
    Each user grabs a pre-provisioned token from the pool on start.
    """

    wait_time = between(0.5, 2.0)
    host = config.api_base

    def on_start(self):
        pool = get_pool()
        if pool.total_provisioned == 0:
            pool.provision(config.num_users)

        self._creds = pool.get()
        self._headers = {
            "Authorization": f"Bearer {self._creds['token']}"
        }
        self._room_ids = pool.room_ids

    def on_stop(self):
        pool = get_pool()
        pool.release(self._creds)

    # ── Tasks (weighted by realistic frequency) ──

    @task(5)
    def list_rooms(self):
        """GET /rooms — most common: users check room list."""
        self.client.get("/rooms", headers=self._headers, name="/rooms")

    @task(3)
    def get_room_users(self):
        """GET /rooms/{id}/users — check who is online."""
        room_id = random.choice(self._room_ids)
        self.client.get(
            f"/rooms/{room_id}/users",
            headers=self._headers,
            name="/rooms/[id]/users",
        )

    @task(3)
    def get_room_messages(self):
        """GET /messages/rooms/{id} — message replay/history via message-service."""
        room_id = random.choice(self._room_ids)
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        self.client.get(
            f"/messages/rooms/{room_id}?since={since}&limit=50",
            headers=self._headers,
            name="/messages/rooms/[id]",
        )

    @task(2)
    def list_files(self):
        """GET /files/room/{id} — list files in a room via file-service."""
        room_id = random.choice(self._room_ids)
        self.client.get(
            f"/files/room/{room_id}",
            headers=self._headers,
            name="/files/room/[id]",
        )


class DbPoolStressUser(HttpUser):
    """
    Aggressive user that fires requests with zero wait time.
    Designed to test DB connection pool exhaustion.

    Run separately:
      locust -f scenarios/http_endpoints.py DbPoolStressUser \
        --headless --users 500 --spawn-rate 50 --run-time 5m
    """

    wait_time = between(0, 0.1)  # Near-zero wait — maximum pressure
    host = config.api_base

    def on_start(self):
        pool = get_pool()
        if pool.total_provisioned == 0:
            pool.provision(config.num_users)

        self._creds = pool.get()
        self._headers = {
            "Authorization": f"Bearer {self._creds['token']}"
        }
        self._room_ids = pool.room_ids

    def on_stop(self):
        get_pool().release(self._creds)

    @task(5)
    def heavy_message_replay(self):
        """Large message replay — forces long DB hold time."""
        room_id = random.choice(self._room_ids)
        self.client.get(
            f"/messages/rooms/{room_id}?since=2020-01-01T00:00:00&limit=500",
            headers=self._headers,
            name="/messages/rooms/[id] (heavy)",
        )

    @task(3)
    def list_rooms(self):
        self.client.get("/rooms", headers=self._headers, name="/rooms (stress)")

    @task(2)
    def get_room_users(self):
        room_id = random.choice(self._room_ids)
        self.client.get(
            f"/rooms/{room_id}/users",
            headers=self._headers,
            name="/rooms/[id]/users (stress)",
        )
