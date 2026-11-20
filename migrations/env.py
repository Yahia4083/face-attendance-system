"""
Alembic Environment Configuration
===================================
Configures the Alembic migration environment.
Reads the database URL from the application settings
and registers all SQLAlchemy models for autogeneration.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Application imports ──────────────────────────────────────────────────────
from app.config import get_settings
from app.infrastructure.database.base import Base

# Import all models so that Base.metadata is fully populated
import app.infrastructure.database.models  # noqa: F401

# ── Alembic Config ───────────────────────────────────────────────────────────
config = context.config

# Override the sqlalchemy.url with the value from .env
settings = get_settings()
# ConfigParser treats percent signs in URL-encoded credentials as interpolation.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


# ── Offline Migrations ───────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL scripts)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online Migrations ────────────────────────────────────────────────────────
def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct database connection)."""
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
