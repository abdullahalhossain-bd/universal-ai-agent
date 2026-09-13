"""
Guards for the Alembic setup itself:

1. The migration chain has exactly one head.
2. Running every migration against an isolated throwaway PostgreSQL schema
   produces the exact same schema Base.metadata describes.

The chain contains Postgres-only DDL, so these tests use the configured
Postgres server and skip clearly when no Postgres server is reachable.
"""

from __future__ import annotations

import os
import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config(database_url: str) -> Config:
    cfg = Config(os.path.join(REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(REPO_ROOT, "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def _postgres_target_url() -> str | None:
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not url.startswith(("postgresql://", "postgresql+")):
        return None
    engine = None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return url
    except Exception:
        return None
    finally:
        if engine is not None:
            engine.dispose()


def _create_scratch_db(base_url: str) -> str:
    """Create an isolated schema on the already-reachable Postgres server.

    Older versions created a second database. That added an unnecessary
    authentication boundary and was the source of CI-only password failures.
    A schema gives the migration test the same isolation while reusing the
    connection that has already been verified by _postgres_target_url().
    """
    url = make_url(base_url)
    schema = f"migration_check_{uuid.uuid4().hex[:12]}"
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    finally:
        engine.dispose()

    scratch_url = url.update_query_dict(
        {"options": f"-csearch_path={schema},public"},
        append=True,
    )
    return str(scratch_url)


def _drop_scratch_db(base_url: str, scratch_url: str) -> None:
    """Drop the isolated migration schema."""
    url = make_url(scratch_url)
    options = url.query.get("options", "")
    marker = "-csearch_path="
    if marker not in options:
        return
    schema = options.split(marker, 1)[1].split(",", 1)[0]
    if not schema:
        return

    engine = create_engine(base_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        engine.dispose()


def _skip_without_postgres() -> str:
    url = _postgres_target_url()
    if url is None:
        pytest.skip(
            "migration chain requires Postgres; set DATABASE_URL or "
            "MIGRATION_TEST_DATABASE_URL to a reachable Postgres"
        )
    return url


def test_migration_chain_has_a_single_head():
    cfg = Config(os.path.join(REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(REPO_ROOT, "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one migration head, found {heads}"


def test_migrations_applied_match_current_models(tmp_path):
    """Apply all revisions to an isolated schema and compare with models."""
    base_url = _skip_without_postgres()
    scratch_url = _create_scratch_db(base_url)
    try:
        cfg = _alembic_config(scratch_url)
        from alembic import command

        command.upgrade(cfg, "head")
        engine = create_engine(scratch_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                from app.db.database import Base

                diffs = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()
        assert diffs == [], f"migration/model schema drift detected: {diffs}"
    finally:
        _drop_scratch_db(base_url, scratch_url)
