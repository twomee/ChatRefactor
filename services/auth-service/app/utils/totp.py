# app/utils/totp.py — Pure TOTP helper functions (no business logic)
"""
Extracted from auth_service.py for Single Responsibility:
- generate_totp_secret: create a random TOTP secret
- get_totp_uri: build an otpauth:// URI for QR codes
- verify_totp: verify a TOTP code against a secret
- check_and_mark_totp_replay: Redis-based replay protection
"""

import pyotp

from app.infrastructure.redis import get_redis


def generate_totp_secret() -> str:
    """Generate a random base32-encoded TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Build an otpauth:// URI suitable for QR code generation."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="cHATBOX")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against the secret, allowing +/- 1 period tolerance."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def check_and_mark_totp_replay(user_id: int, code: str) -> bool:
    """Check for TOTP replay attack and mark the code as used.

    Returns True if the code was already used (replay detected), False otherwise.
    Marks the code as used in Redis with a 90-second TTL (valid_window=1 means
    the code is valid for +-30 seconds = 90-second total window).
    """
    r = get_redis()
    replay_key = f"totp_used:{user_id}:{code}"
    already_used = r.get(replay_key)
    if already_used:
        return True
    r.setex(replay_key, 90, "1")
    return False
