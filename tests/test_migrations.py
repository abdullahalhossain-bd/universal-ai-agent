"""
Guards for the Alembic setup itself:

1. The migration chain has exactly one head (no accidental branching
   from two PRs based off the same parent revision).
2. Running every migration against a fresh database produces the
   exact same schema `Base.metadata` describes — i.e. nobody edited a
   model without generating/committing the matching migration. This
   is the test that would have caught the schema drift this whole
   setup exists to prevent.

The chain now contains Postgres-only DDL (`CREATE EXTENSION vector`,
constraint ALTERs, pgvector column types), so the chain-running tests
execute against a THROWAWAY database on the configured Postgres
server (`MIGRATION_TEST_DATABASE_URL` or `DATABASE_URL`) and skip —
with a clear reason — when no Postgres is reachable. CI provisions a
pgvector/pg16 service container for exactly this.
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
    # Alembic's Config uses ConfigParser interpolation. Database URLs may
    # legitimately contain percent-encoded credentials/query values such as
    # %40, %23 or %2F. Escape percent signs before handing the URL to
    # ConfigParser; ConfigParser will decode %% back to % when Alembic reads it.
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def _postgres_target_url() -> str | None:
    """Return a reachable Postgres URL for migration tests, else None."""
    url = (
        os.environ.get("MIGRATION_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )
    if not url.startswith(("postgresql://", "postgresql+")):
        return None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        engine.dispose()
    except Exception:
        return None
    return url


def _create_scratch_db(base_url: str) -> str:
    """Create a uniquely-named scratch database; return its URL."""
    url = make_url(base_url)
    scratch_name = f"migration_check_{uuid.uuid4().hex[:10]}"

    admin_engine = create_engine(url.set(database=scratch_name), pool_pre_ping=True)
    admin_engine.dispose()

    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{scratch_name}"')
    admin.dispose()

    return str(url.set(database=scratch_name))


def _drop_scratch_db(base_url: str, scratch_url: str) -> None:
    url = make_url(scratch_url)
    scratch_name = url.database
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)'
            )
    except Exception:
        pass
    finally:
        admin.dispose()


def _skip_without_postgres() -> str:
    url = _postgres_target_url()
    if url is None:
        pytest.skip(
            "migration chain requires Postgres (Postgres-only DDL like "
            "CREATE EXTENSION vector); set DATABASE_URL or "
            "MIGRATION_TEST_DATABASE_URL to a reachable Postgres to run"
        )
    return url


def test_migration_chain_has_a_single_head():
    cfg = Config(os.path.join(REPO_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(REPO_ROOT, "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"expected exactly one migration head, found {heads} — "
        "merge the branch with `alembic merge`"
    )


def test_migrations_applied_match_current_models(tmp_path):
    """
    Apply every migration to a throwaway DB, then ask Alembic to
    autogenerate a diff against `Base.metadata` (the live models). A
    non-empty diff means the migration history and the models have
    drifted apart — someone changed a model without a matching
    migration, or a migration doesn't build what the model describes.
    """
    from app.db.database import Base
    import app.db.models  # noqa: F401
    import app.db.admin_audit  # noqa: F401
    import app.db.agent_config  # noqa: F401
    import app.db.visitor  # noqa: F401
    import app.chat.models  # noqa: F401
    import app.knowledge.chunk  # noqa: F401
    import app.usage.models  # noqa: F401

    base_url = _skip_without_postgres()
    scratch_url = _create_scratch_db(base_url)

    try:
        cfg = _alembic_config(scratch_url)

        from alembic import command

        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(conn)
            diff = compare_metadata(migration_ctx, Base.metadata)
        engine.dispose()
    finally:
        _drop_scratch_db(base_url, scratch_url)

    assert diff == [], (
        "alembic migrations do not match app/db models — "
        f"drift detected: {diff}"
    )


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_baseline_migration_runs_cleanly(direction):
    """Every migration's upgrade() and downgrade() must actually run."""
    from alembic import command

    base_url = _skip_without_postgres()
    scratch_url = _create_scratch_db(base_url)

    try:
        cfg = _alembic_config(scratch_url)

        command.upgrade(cfg, "head")
        if direction == "downgrade":
            command.downgrade(cfg, "base")
    finally:
        _drop_scratch_db(base_url, scratch_url)


def _build_legacy_drifted_db(database_url: str) -> None:
    """
    Reproduce, on a scratch Postgres database, the exact drift reported
    against the real production database in the project brief: a
    database that was stamped onto this migration chain (at
    `0006_chat_images`) without ever having the underlying DDL that
    `0001..0006` describe actually applied — see
    `alembic/versions/0007_reconcile_schema_drift.py`'s own docstring
    for the full root-cause explanation.
    """
    engine = create_engine(database_url)
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
        CREATE TABLE stores (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            website_url TEXT,
            plan VARCHAR(20) NOT NULL,
            monthly_budget NUMERIC(12,6) NOT NULL,
            status VARCHAR(30) NOT NULL,
            created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE tenants (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            name VARCHAR(255)
        );
        CREATE TABLE api_keys (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            key_prefix VARCHAR(30) NOT NULL,
            key_hash TEXT NOT NULL,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_api_keys_store_id ON api_keys (store_id);
        CREATE TABLE chat_sessions (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            conversation_key VARCHAR(200) NOT NULL,
            visitor_id VARCHAR(100) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(store_id) REFERENCES stores(id),
            CONSTRAINT uq_chat_sessions_store_conversation UNIQUE (store_id, conversation_key)
        );
        CREATE INDEX ix_chat_sessions_conversation_key ON chat_sessions (conversation_key);
        CREATE INDEX ix_chat_sessions_store_id ON chat_sessions (store_id);
        CREATE TABLE chat_messages (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
        );
        CREATE INDEX ix_chat_messages_session_id ON chat_messages (session_id);
        CREATE TABLE datasources (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            name VARCHAR(100) NOT NULL,
            connector_type VARCHAR(30) NOT NULL,
            connection_url TEXT,
            api_base_url TEXT,
            credential_ref VARCHAR(255),
            table_name VARCHAR(255),
            mapping JSON,
            active BOOLEAN NOT NULL,
            full_sync BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            last_sync_at TIMESTAMP,
            last_sync_status VARCHAR(30),
            last_sync_error TEXT,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_datasources_store_id ON datasources (store_id);
        CREATE INDEX ix_datasources_store_active ON datasources (store_id, active);
        CREATE TABLE products (
            product_id VARCHAR(100) NOT NULL,
            store_id VARCHAR(36) NOT NULL,
            product_name VARCHAR(255) NOT NULL,
            description TEXT,
            selling_price NUMERIC(12,2),
            quantity INTEGER,
            main_image TEXT,
            product_url TEXT,
            PRIMARY KEY (product_id, store_id),
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE TABLE knowledge_pages (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            page_type VARCHAR(30) NOT NULL,
            language VARCHAR(10),
            status VARCHAR(20) NOT NULL,
            http_status INTEGER,
            crawled_at TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_knowledge_pages_store_id ON knowledge_pages (store_id);
        CREATE TABLE knowledge_chunks (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            page_id VARCHAR(36) NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT,
            FOREIGN KEY(page_id) REFERENCES knowledge_pages(id),
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_knowledge_chunks_page_id ON knowledge_chunks (page_id);
        CREATE INDEX ix_knowledge_chunks_store_id ON knowledge_chunks (store_id);
        CREATE TABLE usage_records (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            conversation_id VARCHAR(200) NOT NULL,
            request_id VARCHAR(36) NOT NULL,
            route VARCHAR(50) NOT NULL,
            model VARCHAR(100),
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            estimated_cost FLOAT NOT NULL,
            latency_ms INTEGER NOT NULL,
            cache_hit BOOLEAN NOT NULL,
            status VARCHAR(20) NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_usage_records_conversation_id ON usage_records (conversation_id);
        CREATE INDEX ix_usage_records_expires_at ON usage_records (expires_at);
        CREATE UNIQUE INDEX ux_usage_records_request_id ON usage_records (request_id);
        CREATE INDEX ix_usage_records_request_id ON usage_records (request_id);
        CREATE INDEX ix_usage_records_status ON usage_records (status);
        CREATE INDEX ix_usage_records_store_id ON usage_records (store_id);
        CREATE TABLE chat_images (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            store_id VARCHAR(36) NOT NULL,
            conversation_id VARCHAR(200),
            user_id VARCHAR(100),
            storage_key TEXT NOT NULL,
            mime_type VARCHAR(50) NOT NULL,
            size INTEGER NOT NULL,
            image_hash VARCHAR(64),
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        CREATE INDEX ix_chat_images_store_id ON chat_images (store_id);
        CREATE INDEX ix_chat_images_conversation_id ON chat_images (conversation_id);
        CREATE INDEX ix_chat_images_image_hash ON chat_images (image_hash);
        CREATE TABLE alembic_version (
            version_num VARCHAR(32) NOT NULL PRIMARY KEY
        );
        INSERT INTO alembic_version VALUES ('0006_chat_images');
            """
        )
        conn.commit()
    engine.dispose()


def test_0007_reconciles_real_production_drift():
    """
    Regression test for the exact `alembic check` diff reported
    against production (see the project brief / 0007's docstring):
    a legacy `tenants` table, a missing `api_keys.key_hash` unique
    constraint, `products.quantity` still INTEGER, a missing
    `ix_products_store_id`, and the `usage_records.request_id`
    duplicate-index / missing `created_at`-index drift.

    Builds that exact drifted schema by hand (bypassing 0001-0006,
    like a database that was `alembic stamp`-ed onto this chain
    without the DDL ever running), stamps it at 0006, upgrades to
    head, and asserts both the concrete fixes and a clean
    `compare_metadata` diff against `Base.metadata` — the same
    mechanism `alembic check` uses.
    """
    import sqlalchemy as sa
    from alembic import command
    from app.db.database import Base
    import app.db.models  # noqa: F401
    import app.db.admin_audit  # noqa: F401
    import app.db.agent_config  # noqa: F401
    import app.db.visitor  # noqa: F401
    import app.chat.models  # noqa: F401
    import app.knowledge.chunk  # noqa: F401
    import app.usage.models  # noqa: F401

    base_url = _skip_without_postgres()
    scratch_url = _create_scratch_db(base_url)

    try:
        _build_legacy_drifted_db(scratch_url)

        cfg = _alembic_config(scratch_url)
        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        inspector = sa.inspect(engine)

        # 1) obsolete `tenants` table is gone.
        assert "tenants" not in inspector.get_table_names()

        # 2) api_keys.key_hash has a uniqueness guarantee.
        has_unique_key_hash = any(
            uc["column_names"] == ["key_hash"]
            for uc in inspector.get_unique_constraints("api_keys")
        ) or any(
            idx["unique"] and idx["column_names"] == ["key_hash"]
            for idx in inspector.get_indexes("api_keys")
        )
        assert has_unique_key_hash

        # 3) products.quantity is Numeric, not Integer.
        quantity_col = next(
            c for c in inspector.get_columns("products") if c["name"] == "quantity"
        )
        assert isinstance(quantity_col["type"], sa.Numeric)

        # 4) ix_products_store_id exists.
        assert "ix_products_store_id" in {
            idx["name"] for idx in inspector.get_indexes("products")
        }

        # 6) usage_records.request_id: no more duplicate index, and the
        #    canonical index is unique.
        usage_indexes = {
            idx["name"]: idx for idx in inspector.get_indexes("usage_records")
        }
        assert "ux_usage_records_request_id" not in usage_indexes
        assert usage_indexes["ix_usage_records_request_id"]["unique"]

        # 7) ix_usage_records_created_at exists.
        assert "ix_usage_records_created_at" in usage_indexes

        # Finally: the same check `alembic check` runs — a clean diff
        # against the live models.
        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(conn)
            diff = compare_metadata(migration_ctx, Base.metadata)
    finally:
        _drop_scratch_db(base_url, scratch_url)

    assert diff == [], f"drifted database not fully reconciled: {diff}"


def test_no_migration_creates_a_table_owned_by_an_earlier_migration(tmp_path):
    """
    Regression guard for the `datasources` duplicate-table bug found
    while auditing the chain: `0001_baseline_schema.py` and
    `0005_datasources.py` both had `op.create_table("datasources",
    ...)`. Because 0005's copy is guarded with "if not exists", it
    silently never ran in any real environment — 0001 always runs
    first — so 0005's `server_default=` values for
    name/active/full_sync/created_at/updated_at were dead code (see
    0007_reconcile_schema_drift.py's docstring for the full story and
    fix). This test parses every migration file's `upgrade()` source
    for `op.create_table("<name>", ...)` calls and fails if any table
    name is claimed by more than one migration, so this class of bug
    can't silently reappear.
    """
    import ast

    versions_dir = os.path.join(REPO_ROOT, "alembic", "versions")
    owners: dict[str, list[str]] = {}

    for filename in sorted(os.listdir(versions_dir)):
        if not filename.endswith(".py"):
            continue
        path = os.path.join(versions_dir, filename)
        tree = ast.parse(
            open(path, encoding="utf-8-sig").read(), filename=path
        )

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "op"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                table_name = node.args[0].value
                owners.setdefault(table_name, []).append(filename)

    duplicates = {
        table: files for table, files in owners.items() if len(files) > 1
    }
    assert duplicates == {}, (
        f"table(s) created by more than one migration (the later "
        f"create_table call is dead code in every real environment, "
        f"since the earlier one already ran): {duplicates}"
    )
