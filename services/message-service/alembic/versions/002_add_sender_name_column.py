"""Add sender_name column to messages table

The initial migration (001) created the messages table without sender_name,
which was added to the ORM model later to support denormalized message history
display without requiring cross-service lookups to auth-service.

Revision ID: 002
Revises: 001
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add sender_name column to messages table.

    Uses ADD COLUMN IF NOT EXISTS for idempotent deployment — safe to run
    against a database that already has the column (e.g., fresh deploys where
    001 is replaced with a schema that includes sender_name).
    """
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(64)")


def downgrade() -> None:
    """Drop sender_name column from messages table."""
    op.drop_column("messages", "sender_name")
