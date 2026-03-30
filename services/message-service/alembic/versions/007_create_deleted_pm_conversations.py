"""Create deleted_pm_conversations table for per-user PM conversation deletion

Tracks when a user deletes a PM conversation from their view. Messages
before deleted_at are hidden from the user but NOT removed from the
database -- the other participant's view is unaffected.

Revision ID: 007
Revises: 006
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the deleted_pm_conversations table.

    Each row represents a user deleting their view of a PM conversation
    with another user. The UNIQUE constraint ensures at most one deletion
    record per (user_id, other_user_id) pair -- re-deleting updates the
    timestamp.
    """
    op.create_table(
        "deleted_pm_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("other_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "other_user_id", name="uq_deleted_pm"
        ),
    )
    op.create_index(
        "idx_deleted_pm_user",
        "deleted_pm_conversations",
        ["user_id"],
    )


def downgrade() -> None:
    """Drop the deleted_pm_conversations table."""
    op.drop_index("idx_deleted_pm_user", table_name="deleted_pm_conversations")
    op.drop_table("deleted_pm_conversations")
