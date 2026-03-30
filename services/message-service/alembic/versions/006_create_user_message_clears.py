"""Create user_message_clears table for per-user conversation clear history

Tracks when a user clears their view of a conversation (room or PM).
Messages before cleared_at are hidden from the user but NOT deleted from
the database -- other users still see them.

Revision ID: 006
Revises: 005
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the user_message_clears table.

    Each row represents a user clearing their view of a specific context
    (room or PM conversation). The UNIQUE constraint ensures at most one
    clear record per user per context -- re-clearing updates the timestamp.
    """
    op.create_table(
        "user_message_clears",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("context_type", sa.String(10), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=False),
        sa.Column(
            "cleared_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "context_type", "context_id", name="uq_user_clear"
        ),
        sa.CheckConstraint(
            "context_type IN ('room', 'pm')", name="ck_context_type"
        ),
    )
    op.create_index(
        "idx_umc_lookup",
        "user_message_clears",
        ["user_id", "context_type", "context_id"],
    )


def downgrade() -> None:
    """Drop the user_message_clears table."""
    op.drop_index("idx_umc_lookup", table_name="user_message_clears")
    op.drop_table("user_message_clears")
