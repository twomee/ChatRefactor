"""Add is_file and file_id columns to messages table

Enables PM file messages to be persisted to the database so they
survive page refreshes. is_file flags the row as a file upload;
file_id references the file in the file-service (no FK — different DB).

Revision ID: 009
Revises: 008
Create Date: 2026-03-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_file", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "messages",
        sa.Column("file_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "file_id")
    op.drop_column("messages", "is_file")
