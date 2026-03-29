"""Add 2FA fields to users table

Adds TOTP-based two-factor authentication support:
- totp_secret: base32-encoded TOTP secret key (nullable — null means 2FA not set up)
- is_2fa_enabled: boolean flag (default false) — true when user has verified their TOTP setup
- backup_codes: JSON-serialized array of hashed backup codes (nullable)

Revision ID: 003
Revises: 002
Create Date: 2026-03-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("totp_secret", sa.String(32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_2fa_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("backup_codes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "backup_codes")
    op.drop_column("users", "is_2fa_enabled")
    op.drop_column("users", "totp_secret")
