# app/utils/totp.py — Pure TOTP helper functions (no business logic)
"""
Extracted from auth_service.py for Single Responsibility:
- generate_totp_secret: create a random TOTP secret
- get_totp_uri: build an otpauth:// URI for QR codes
- verify_totp: verify a TOTP code against a secret
"""

import pyotp


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
