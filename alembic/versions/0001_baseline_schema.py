"""baseline schema

Snapshot of the schema `Base.metadata.create_all()` (app/main.py's dev
fallback) produces today, turned into a real, reviewable migration.
This is the migration to run once against any environment that only
ever had `AUTO_CREATE_TABLES=true` create its tables — Alembic's
`alembic_version` table won't exist yet there, so this revision's
`upgrade()` must match what's already on disk exactly (it does: see
alembic/README.md for how this was verified against the ORM models).

Revision ID: 0001
Revises:
Create Date: 2026-08-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _knowledge_embedding_column() -> sa.types.TypeEngine:
    """
    Mirror app.knowledge.vector_support's runtime probe, but decided
    once at migration time rather than on every app start — a schema's
    column type should not silently change between deploys depending
    on what happened to be installed when a process booted.

    Uses VECTOR(384) when both the `pgvector` Python package and the
    Postgres `vector` extension are available on the target database;
    falls back to Text otherwise (keyword search still works, semantic
    search is disabled). See app/knowledge/chunk.py for the runtime
    counterpart this replaces for anything migrated through here.
    """

    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        # sqlite (local dev / this project's test suite) — always Text.
        return sa.Text()

    try:
        import pgvector.sqlalchemy  # noqa: F401
    except ImportError:
        return sa.Text()

    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        present = bind.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).first()
    except Exception:
        return sa.Text()

    if not present:
        return sa.Text()

    from pgvector.sqlalchemy import Vector

    return Vector(384)


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column(
            "monthly_budget", sa.Numeric(precision=12, scale=6), nullable=False
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("key_prefix", sa.String(length=30), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(
        "ix_api_keys_store_id", "api_keys", ["store_id"], unique=False
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_key", sa.String(length=200), nullable=False),
        sa.Column("visitor_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "conversation_key",
            name="uq_chat_sessions_store_conversation",
        ),
    )
    op.create_index(
        "ix_chat_sessions_conversation_key",
        "chat_sessions",
        ["conversation_key"],
        unique=False,
    )
    op.create_index(
        "ix_chat_sessions_store_id", "chat_sessions", ["store_id"], unique=False
    )

    op.create_table(
        "datasources",
        # NOTE: this table is also (redundantly) defined in
        # 0005_datasources.py, which no-ops here since the table
        # already exists by the time it runs — see that file's
        # docstring and 0007_reconcile_schema_drift.py for the fix.
        # Left as-is: this table creation has already run in every
        # real environment, and this is the version that actually
        # took effect.
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("connector_type", sa.String(length=30), nullable=False),
        # Encrypted at rest (app.connectors.credential_store) — this
        # column always stores Fernet ciphertext, never a plaintext
        # merchant DB connection string. Text, same as before; the
        # encryption is application-level, not a DB column-type change.
        sa.Column("connection_url", sa.Text(), nullable=True),
        sa.Column("api_base_url", sa.Text(), nullable=True),
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
        sa.Column("table_name", sa.String(length=255), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("full_sync", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sa.String(length=30), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_datasources_store_id", "datasources", ["store_id"], unique=False
    )

    op.create_table(
        "knowledge_pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("page_type", sa.String(length=30), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("crawled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_pages_store_id", "knowledge_pages", ["store_id"], unique=False
    )

    op.create_table(
        "products",
        sa.Column("product_id", sa.String(length=100), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "selling_price", sa.Numeric(precision=12, scale=2), nullable=True
        ),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("main_image", sa.Text(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("product_id", "store_id"),
    )
    op.create_index(
        "ix_products_store_id", "products", ["store_id"], unique=False
    )

    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=200), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("route", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_usage_records_conversation_id",
        "usage_records",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_created_at", "usage_records", ["created_at"], unique=False
    )
    op.create_index(
        "ix_usage_records_expires_at", "usage_records", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_usage_records_request_id", "usage_records", ["request_id"], unique=True
    )
    op.create_index(
        "ix_usage_records_status", "usage_records", ["status"], unique=False
    )
    op.create_index(
        "ix_usage_records_store_id", "usage_records", ["store_id"], unique=False
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_session_id", "chat_messages", ["session_id"], unique=False
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("page_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", _knowledge_embedding_column(), nullable=True),
        sa.ForeignKeyConstraint(["page_id"], ["knowledge_pages.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_chunks_page_id", "knowledge_chunks", ["page_id"], unique=False
    )
    op.create_index(
        "ix_knowledge_chunks_store_id", "knowledge_chunks", ["store_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("chat_messages")
    op.drop_table("usage_records")
    op.drop_table("products")
    op.drop_table("knowledge_pages")

    # Guarded: 0005_datasources' own downgrade() already drops this
    # table when it ran (it owns the table on any chain that applied
    # 0005 on top of this baseline), so by the time a full downgrade
    # reaches here it may already be gone. Only 0001's upgrade() ever
    # created it directly (for environments migrated straight from
    # `Base.metadata.create_all()`), so this stays a no-op instead of
    # erroring either way.
    import sqlalchemy as sa

    conn = op.get_bind()
    if "datasources" in sa.inspect(conn).get_table_names():
        op.drop_table("datasources")

    op.drop_table("chat_sessions")
    op.drop_table("api_keys")
    op.drop_table("stores")
