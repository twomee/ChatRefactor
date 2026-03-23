# alembic/env.py — Alembic environment configuration for Auth Service
"""
Imports Base metadata from app.core.database and DATABASE_URL from app.core.config
so that Alembic can detect model changes and generate/run migrations.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the auth-service root to sys.path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import DATABASE_URL  # noqa: E402
from app.core.database import Base  # noqa: E402

# Import all models so their metadata is registered with Base
from app.models import User  # noqa: E402, F401

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting to DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to DB and applies changes."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
