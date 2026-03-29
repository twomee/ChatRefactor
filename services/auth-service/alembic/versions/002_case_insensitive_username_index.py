"""Replace case-sensitive username unique index with case-insensitive one

The application now performs case-insensitive username lookups via
func.lower(User.username). Without a matching functional index, the DB's
unique constraint remains case-sensitive, allowing "Alice" and "alice" to
coexist via race conditions. This migration drops the old index and creates
a case-insensitive unique index using lower(username).

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old case-sensitive unique index
    op.drop_index("ix_users_username", table_name="users")

    # Create a case-insensitive unique index using lower()
    # This ensures "Alice" and "alice" are treated as duplicates at the DB level,
    # matching the application's case-insensitive lookup behavior.
    op.execute(
        "CREATE UNIQUE INDEX ix_users_username_lower ON users (lower(username))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_users_username_lower")
    op.create_index("ix_users_username", "users", ["username"], unique=True)
