from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic Config object
config = context.config

# Set up logging from ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so autogenerate can see them
from backend.app.db.base import Base  # noqa: E402
import backend.app.db.models  # noqa: E402, F401 — side-effect: registers models

target_metadata = Base.metadata

# Allow DATABASE_URL env var to override alembic.ini value
# Strip the aiosqlite driver prefix for sync migrations
_db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if _db_url.startswith("sqlite+aiosqlite"):
    _db_url = _db_url.replace("sqlite+aiosqlite", "sqlite", 1)
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
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
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
