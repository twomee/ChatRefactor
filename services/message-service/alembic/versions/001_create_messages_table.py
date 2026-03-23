"""Create messages table

Revision ID: 001
Revises: None
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the messages table.

    NO foreign keys — in the microservice architecture, users and rooms live in
    separate databases (auth-service and chat-service respectively). Referential
    integrity is enforced at the application level.
    """
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("recipient_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Unique index on message_id for idempotent Kafka writes
    op.create_index("ix_messages_message_id", "messages", ["message_id"], unique=True)
    # Index on room_id + sent_at for efficient replay/history queries
    op.create_index("ix_messages_room_sent", "messages", ["room_id", "sent_at"])


def downgrade() -> None:
    """Drop the messages table."""
    op.drop_index("ix_messages_room_sent")
    op.drop_index("ix_messages_message_id")
    op.drop_table("messages")
