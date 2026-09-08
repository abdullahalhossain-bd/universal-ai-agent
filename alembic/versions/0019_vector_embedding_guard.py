"""ensure pgvector embedding column + ivfflat index for stamped legacy DBs

Revision ID: 0019_vector_embedding_guard
Revises: 0018_merge_datasource_ownership

Databases that were `alembic stamp`-ed onto this chain mid-way (the
production database was stamped at `0006_chat_images` without the DDL
ever running — see 0007's docstring) skip 0002's optional TEXT ->
VECTOR(384) conversion forever, because 0002 is below the stamp point.
On a pgvector-capable server the ORM then resolves
`knowledge_chunks.embedding` to `Vector(384)` while the stored column
is still TEXT — semantic search writes would fail at runtime.

This migration re-applies 0002's guarded conversion at the chain head:
- no-op on databases whose embedding column is already `vector`
- converts TEXT -> VECTOR(384) when the pgvector extension is available
- leaves everything untouched when pgvector is unavailable (semantic
  search simply stays disabled — nothing is destroyed)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0019_vector_embedding_guard"
down_revision: Union[str, None] = "0018_merge_datasource_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name != "postgresql":
        # sqlite never had a vector column type; nothing to do.
        return

    # Mirror 0002: make sure the extension exists (it does on every
    # pgvector-enabled server), then check the catalog directly.
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    pgvector_available = conn.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).first()

    if not pgvector_available:
        return

    column_is_vector = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'knowledge_chunks' "
            "AND column_name = 'embedding' "
            "AND udt_name = 'vector'"
        )
    ).first()

    if column_is_vector:
        # Fresh-migrated database: 0002 already did the conversion.
        # Only make sure the ivfflat index exists.
        op.execute(
            "CREATE INDEX IF NOT EXISTS "
            "ix_knowledge_chunks_embedding "
            "ON knowledge_chunks USING ivfflat (embedding vector_l2_ops) "
            "WITH (lists = 100)"
        )
        return

    # A TEXT column that was indexed by 0011's plain btree index
    # cannot be ALTERed in place (type `vector` has no btree
    # opclass), so drop that index first — it is recreated as an
    # ivfflat index right after the conversion.
    existing_indexes = {
        index["name"]
        for index in sa.inspect(conn).get_indexes("knowledge_chunks")
    }
    if "ix_knowledge_chunks_embedding" in existing_indexes:
        op.drop_index(
            "ix_knowledge_chunks_embedding",
            table_name="knowledge_chunks",
        )

    # NULL embeddings survive the cast; a non-empty TEXT value that
    # is not valid vector syntax aborts the migration loudly — never
    # silently converted (same policy as 0002).
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector(384) "
        "USING embedding::vector"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_knowledge_chunks_embedding "
        "ON knowledge_chunks USING ivfflat (embedding vector_l2_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    # The pgvector type change is intentionally NOT reversed:
    # converting vector -> text would be lossy in formatting and
    # would break any store that already relies on semantic search.
    pass
