"""Add full-text search support to messages table

Adds a tsvector column with a GIN index and a trigger that automatically
populates the search vector on INSERT/UPDATE. Backfills existing rows so
they are immediately searchable.

PostgreSQL-specific: uses raw SQL because SQLAlchemy does not natively
support tsvector columns, GIN indexes, or PL/pgSQL trigger functions.

Revision ID: 005
Revises: 004
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add search_vector tsvector column, GIN index, and auto-populate trigger.

    1. Add the tsvector column (nullable — avoids NOT NULL on existing rows).
    2. Create the trigger function that converts content to a search vector.
    3. Attach the trigger to fire BEFORE INSERT or UPDATE OF content.
    4. Backfill existing rows so they are immediately searchable.
    5. Create a GIN index for fast full-text queries.

    All statements use IF NOT EXISTS / OR REPLACE for idempotent deployment.
    """
    op.execute("""
        ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION messages_search_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS messages_search_update ON messages;
        CREATE TRIGGER messages_search_update
            BEFORE INSERT OR UPDATE OF content ON messages
            FOR EACH ROW EXECUTE FUNCTION messages_search_trigger();
    """)

    op.execute("""
        UPDATE messages SET search_vector = to_tsvector('english', COALESCE(content, ''))
            WHERE search_vector IS NULL;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_messages_search_vector
            ON messages USING GIN(search_vector);
    """)


def downgrade() -> None:
    """Remove full-text search infrastructure."""
    op.execute("DROP INDEX IF EXISTS ix_messages_search_vector;")
    op.execute("DROP TRIGGER IF EXISTS messages_search_update ON messages;")
    op.execute("DROP FUNCTION IF EXISTS messages_search_trigger();")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS search_vector;")
