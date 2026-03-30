"""Add edited_at and is_deleted columns to messages table

Supports message editing and soft-deletion. edited_at is set when a message
is modified by its author. is_deleted flags soft-deleted messages whose content
is replaced with "[deleted]".

Revision ID: 003
Revises: 002
Create Date: 2026-03-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add edited_at and is_deleted columns to messages table.

    Uses ADD COLUMN IF NOT EXISTS for idempotent deployment — safe to run
    against a database that already has the columns.
    """
    op.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    """Drop edited_at and is_deleted columns from messages table."""
    op.drop_column("messages", "is_deleted")
    op.drop_column("messages", "edited_at")
