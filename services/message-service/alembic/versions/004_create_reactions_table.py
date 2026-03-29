"""Create reactions table for emoji reactions on messages

Revision ID: 004
Revises: 003
Create Date: 2026-03-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the reactions table for emoji reactions on messages.

    Each row represents a single user's reaction (one emoji) on a message.
    The UNIQUE constraint prevents duplicate reactions (same user + same emoji
    on the same message).
    """
    op.create_table(
        "reactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("emoji", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "message_id", "user_id", "emoji", name="uq_reaction_per_user_per_emoji"
        ),
    )
    op.create_index("ix_reactions_message_id", "reactions", ["message_id"])


def downgrade() -> None:
    """Drop the reactions table."""
    op.drop_index("ix_reactions_message_id", table_name="reactions")
    op.drop_table("reactions")
