"""Fix the pgvector ivfflat opclass so semantic search can actually use it.

Revision ID: 0043_vector_cosine_index
Revises: 0042_billing_webhook_idempotency

Problem
-------
Migrations 0002 / 0019 created the ivfflat index with ``vector_l2_ops``:

    CREATE INDEX ... USING ivfflat (embedding vector_l2_ops) WITH (lists=100)

but the application queries cosine distance (``<=>``, see
``app/knowledge/vector_search.py``). An ivfflat index only serves queries
that use the operator of its opclass, so ``ORDER BY embedding <=> :q``
could never use this index: every semantic/hybrid search degraded to a
sequential scan over ALL stores' chunks as soon as a store had real data.

Fix
---
Recreate the same index with ``vector_cosine_ops`` (the opclass that owns
the ``<=>`` operator). Embeddings are L2-normalized at generation time
(``app/knowledge/embedding.py``), so scores remain identical — only the
plan changes, from Seq Scan to Index Scan.

Runs only when the embedding column is actually ``vector`` (pgvector
enabled); a TEXT column (pgvector unavailable) is left untouched, matching
the guard policy of 0002/0019.
"""

from alembic import op
import sqlalchemy as sa

revision = "0043_vector_cosine_index"
down_revision = "0042_billing_webhook_idempotency"
branch_labels = None
depends_on = None

_L2_INDEX = "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding ON knowledge_chunks USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)"
_COSINE_INDEX = "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"


def _embedding_column_is_vector(conn) -> bool:
    return (
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' "
                "AND column_name = 'embedding' "
                "AND udt_name = 'vector'"
            )
        ).first()
        is not None
    )


def _existing_index_opclass(conn) -> str | None:
    """Return the opclass of the current embedding ivfflat index, if any."""
    row = conn.execute(
        sa.text(
            "SELECT amname, opclass.opcname "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_am am ON am.oid = c.relam "
            "JOIN pg_attribute att ON att.attrelid = i.indrelid AND att.attnum = ANY(i.indkey::int2[]) "
            "JOIN pg_opclass opclass ON opclass.oid = i.indclass[0] "
            "WHERE c.relname = 'ix_knowledge_chunks_embedding'"
        )
    ).first()
    if row is None:
        return None
    return str(row[1])


def upgrade() -> None:
    conn = op.get_bind()
    if not _embedding_column_is_vector(conn):
        # pgvector never enabled on this database: the column is TEXT and
        # has no ivfflat index. Nothing to fix.
        return
    current = _existing_index_opclass(conn)
    if current == "vector_cosine_ops":
        return
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute(_COSINE_INDEX)


def downgrade() -> None:
    conn = op.get_bind()
    if not _embedding_column_is_vector(conn):
        return
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute(_L2_INDEX)
