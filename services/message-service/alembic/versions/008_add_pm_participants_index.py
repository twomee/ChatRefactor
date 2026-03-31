"""Add partial index on messages for PM participant lookups

Speeds up GET /messages/pm/history/{username} queries which filter by
(is_private, sender_id, recipient_id).

Revision ID: 008
Revises: 007
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial index on messages for PM participant queries."""
    op.create_index(
        "idx_messages_pm_participants",
        "messages",
        ["sender_id", "recipient_id"],
        postgresql_where=sa.text("is_private = true"),
    )


def downgrade() -> None:
    """Remove PM participants index."""
    op.drop_index("idx_messages_pm_participants", table_name="messages")
