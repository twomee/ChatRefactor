"""Widen totp_secret column to accommodate encrypted ciphertext

Encrypting the TOTP secret with AES-256-GCM produces a base64-encoded blob
of approximately 60–80 characters (12-byte nonce + 32-byte secret + 16-byte
GCM tag, all base64-encoded). String(256) gives comfortable headroom.

Revision ID: 004
Revises: 003
Create Date: 2026-03-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(32),
        type_=sa.String(256),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(256),
        type_=sa.String(32),
        nullable=True,
    )
