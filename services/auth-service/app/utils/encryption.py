"""Symmetric encryption utility for sensitive fields stored in the database."""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    """Read and validate the AES-256 encryption key from environment."""
    key_hex = os.environ.get("TOTP_ENCRYPTION_KEY", "")
    if not key_hex:
        raise RuntimeError(
            "TOTP_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("TOTP_ENCRYPTION_KEY must be exactly 32 bytes (64 hex chars)")
    return key


def encrypt_totp_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for database storage. Returns base64-encoded ciphertext."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Encode nonce + ciphertext together as base64
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_totp_secret(encrypted: str) -> str:
    """Decrypt a TOTP secret from database storage."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
