"""
Alembic environment.

Deliberately imports the same model set app/main.py labels "Active ORM
Models" — this is the single source of truth for what schema exists.
Do NOT import the legacy/duplicate model modules under app.catalog,
app.models, app.connectors.models, app.tenants — those sit on a
different, disconnected `Base` (app.db.session.Base) that nothing in
the running app actually uses; see app/ARCHITECTURE_CLEANUP.md. If a
future cleanup deletes those modules, nothing here needs to change.
"""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

# The standalone `alembic` console script does not always add the
# repository root to sys.path on Windows. Anchor imports to this file
# so migrations behave the same via `alembic` and `python -m alembic`.
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- App wiring -------------------------------------------------------
# One source of truth for the DB URL: app.core.config.settings (same
# DATABASE_URL env var the running app uses). Never duplicate it in
# alembic.ini.
from app.core.config import settings  # noqa: E402
from app.db.database import Base  # noqa: E402

# Populate Base.metadata by importing every module that defines an
# active model — mirrors app/main.py's "Active ORM Models" section.
from app.db.models import (  # noqa: E402,F401
    APIKey,
    ChatImage,
    DataSource,
    Product,
    Store,
    User,
)
from app.chat.models import ChatSession, ChatMessage  # noqa: E402,F401
from app.knowledge.chunk import KnowledgePage, KnowledgeChunk  # noqa: E402,F401
from app.usage.models import UsageRecord  # noqa: E402,F401

target_metadata = Base.metadata

# Prefer a URL already set on the Config object (e.g. by
# tests/test_migrations.py pointing this at a scratch sqlite DB) over
# the app's configured DATABASE_URL, so migrations stay testable
# against a throwaway database without needing a real Postgres.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`--sql`)."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # sqlite (used for local dev / this project's own test
            # suite) can't ALTER a column in place; batch mode
            # recreates the table under the hood instead. Harmless
            # no-op on Postgres, which supports ALTER natively.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()