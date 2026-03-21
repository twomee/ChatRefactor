"""
Micro-benchmarks for authentication operations.

Measures the throughput ceilings imposed by:
  - Argon2 password hashing (~100ms by design — security vs performance tradeoff)
  - Argon2 password verification
  - JWT token encoding
  - JWT token decoding

Why this matters:
  If Argon2 takes 100ms, a single worker can do max 10 logins/sec.
  With 8 Gunicorn workers = 80 logins/sec theoretical max.
  This benchmark quantifies that ceiling.

Usage:
  cd loadtests
  pytest benchmarks/bench_auth.py --benchmark-only -v
  pytest benchmarks/bench_auth.py --benchmark-only --benchmark-json=reports/bench_auth.json
"""

from datetime import datetime, timedelta, timezone

import pytest

# ── Argon2 Benchmarks ──


def test_argon2_hash(benchmark):
    """
    Measure password hashing time.
    Argon2 is intentionally slow — this is the floor for register throughput.
    """
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    benchmark(ph.hash, "loadtest_password_123")


def test_argon2_verify(benchmark):
    """
    Measure password verification time.
    This is the floor for login throughput.
    """
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    hashed = ph.hash("loadtest_password_123")
    benchmark(ph.verify, hashed, "loadtest_password_123")


# ── JWT Benchmarks ──


def test_jwt_encode(benchmark):
    """Measure JWT creation speed. Called once per login."""
    from jose import jwt

    payload = {
        "sub": "42",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    benchmark(
        jwt.encode,
        payload,
        "test-secret-key-for-benchmark",
        algorithm="HS256",
    )


def test_jwt_decode(benchmark):
    """
    Measure JWT decode speed. Called on EVERY authenticated request.
    This is the per-request auth overhead.
    """
    from jose import jwt

    token = jwt.encode(
        {
            "sub": "42",
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        },
        "test-secret-key-for-benchmark",
        algorithm="HS256",
    )
    benchmark(
        jwt.decode,
        token,
        "test-secret-key-for-benchmark",
        algorithms=["HS256"],
    )


# ── Combined: Hash + Verify (full registration cost) ──


def test_full_register_cost(benchmark):
    """
    Measure full registration cost: hash password.
    This is the most expensive single operation in the auth flow.
    """
    from argon2 import PasswordHasher

    ph = PasswordHasher()

    def register_flow():
        ph.hash("loadtest_password_123")

    benchmark(register_flow)


def test_full_login_cost(benchmark):
    """
    Measure full login cost: verify password + encode JWT.
    """
    from argon2 import PasswordHasher
    from jose import jwt

    ph = PasswordHasher()
    hashed = ph.hash("loadtest_password_123")

    def login_flow():
        ph.verify(hashed, "loadtest_password_123")
        jwt.encode(
            {
                "sub": "42",
                "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            },
            "test-secret-key-for-benchmark",
            algorithm="HS256",
        )

    benchmark(login_flow)
