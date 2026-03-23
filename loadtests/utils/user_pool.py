"""
Pre-provisions load test users and caches their JWT tokens.

Why this exists:
  - Rate limiting: register = 5/min, login = 10/min per IP
  - Without pre-provisioned users, load tests hit 429 errors in seconds
  - Strategy: create users once before tests, reuse tokens across scenarios

Usage:
  # As a module (from scripts)
  pool = UserPool(config)
  pool.provision(100)
  creds = pool.get()     # {"username": "...", "token": "..."}
  pool.release(creds)    # Return to pool for reuse

  # CLI
  python -m utils.user_pool --provision 100
"""

import logging
import queue
import sys
import threading
import time
from pathlib import Path

import requests

# Allow imports when run from loadtests/ or as a submodule
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LoadTestConfig, config as default_config

logger = logging.getLogger(__name__)


class UserPool:
    """Thread-safe pool of pre-provisioned users with cached JWT tokens."""

    def __init__(self, cfg: LoadTestConfig | None = None):
        self.cfg = cfg or default_config
        self._available: queue.Queue[dict] = queue.Queue()
        self._all_users: list[dict] = []
        self._lock = threading.Lock()
        self._room_ids: list[int] = []

    def provision(self, count: int | None = None) -> None:
        """Register and login `count` users. Idempotent — handles 409 (already exists)."""
        count = count or self.cfg.num_users
        session = requests.Session()
        base = self.cfg.api_base

        logger.info(f"Provisioning {count} users against {base} ...")
        start = time.monotonic()

        # First, ensure admin exists and login to get admin token
        admin_token = self._login_admin(session, base)

        # Fetch room IDs
        self._room_ids = self._fetch_room_ids(session, base, admin_token)
        logger.info(f"Found rooms: {self._room_ids}")

        provisioned = 0
        failed = 0

        for i in range(count):
            username = f"{self.cfg.user_prefix}_{i:04d}"
            password = self.cfg.user_password

            # Register (may already exist — 409 is fine)
            try:
                resp = session.post(
                    f"{base}/auth/register",
                    json={"username": username, "password": password},
                    timeout=10,
                )
                if resp.status_code not in (201, 200, 409):
                    logger.warning(
                        f"Register {username} failed: {resp.status_code} {resp.text}"
                    )
                    failed += 1
                    continue
            except requests.RequestException as e:
                logger.warning(f"Register {username} error: {e}")
                failed += 1
                continue

            # Login to get token
            try:
                resp = session.post(
                    f"{base}/auth/login",
                    json={"username": username, "password": password},
                    timeout=10,
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"Login {username} failed: {resp.status_code} {resp.text}"
                    )
                    failed += 1
                    continue

                data = resp.json()
                creds = {
                    "username": username,
                    "password": password,
                    "token": data["access_token"],
                }
                self._available.put(creds)
                self._all_users.append(creds)
                provisioned += 1
            except requests.RequestException as e:
                logger.warning(f"Login {username} error: {e}")
                failed += 1
                continue

        elapsed = time.monotonic() - start
        logger.info(
            f"Provisioned {provisioned}/{count} users in {elapsed:.1f}s "
            f"({failed} failures)"
        )

    def _login_admin(self, session: requests.Session, base: str) -> str:
        """Login the admin user and return the token."""
        # Register admin (may already exist)
        session.post(
            f"{base}/auth/register",
            json={
                "username": self.cfg.admin_username,
                "password": self.cfg.admin_password,
            },
            timeout=10,
        )

        resp = session.post(
            f"{base}/auth/login",
            json={
                "username": self.cfg.admin_username,
                "password": self.cfg.admin_password,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Admin login failed: {resp.status_code} {resp.text}"
            )
        return resp.json()["access_token"]

    def _fetch_room_ids(
        self, session: requests.Session, base: str, token: str
    ) -> list[int]:
        """Get list of available room IDs."""
        resp = session.get(
            f"{base}/rooms",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch rooms: {resp.status_code}")
            return [1, 2, 3]  # Fallback to default IDs
        return [r["id"] for r in resp.json()]

    @property
    def room_ids(self) -> list[int]:
        return self._room_ids or [1, 2, 3]

    @property
    def size(self) -> int:
        return self._available.qsize()

    @property
    def total_provisioned(self) -> int:
        return len(self._all_users)

    def get(self, timeout: float = 30) -> dict:
        """Get a user's credentials. Blocks until one is available."""
        try:
            return self._available.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError(
                f"No users available in pool (total: {len(self._all_users)}, "
                f"available: {self._available.qsize()}). "
                "Did you call provision() first?"
            )

    def release(self, creds: dict) -> None:
        """Return credentials to the pool after use."""
        self._available.put(creds)

    def get_all(self) -> list[dict]:
        """Get all provisioned user credentials (for read-only access)."""
        return list(self._all_users)


# Module-level singleton
_pool: UserPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> UserPool:
    """Get or create the singleton user pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = UserPool()
    return _pool


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Provision load test users")
    parser.add_argument(
        "--provision", type=int, default=100, help="Number of users to create"
    )
    parser.add_argument("--env", type=str, help="Path to .env file")
    args = parser.parse_args()

    if args.env:
        cfg = LoadTestConfig.from_env(args.env)
    else:
        cfg = default_config

    pool = UserPool(cfg)
    pool.provision(args.provision)
    print(f"\nReady: {pool.size} users available, rooms: {pool.room_ids}")
