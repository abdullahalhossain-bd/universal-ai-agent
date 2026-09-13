"""chat_sessions unique (store_id, conversation_key) + pgvector upgrade

Two independent hardening steps:

1. Add `uq_chat_sessions_store_conversation` — one conversation
   key per store. Protects the check-then-insert race in
   `ChatService._get_or_create_session`. The constraint is only
   added when it does not already exist AND no duplicate rows
   are present; if duplicates exist the migration fails loudly
   instead of silently destroying data (they must be merged by
   hand, which is a data decision, not a schema decision).

2. When the pgvector extension is available, convert
   `knowledge_chunks.embedding` from TEXT to VECTOR(384) and add
   an ivfflat index. When pgvector is unavailable this step
   no-ops and the application continues to use keyword search.

Revision ID: 0002_constraints
Revises: 0001_baseline
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0002_constraints"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    # -------------------------------------------------
    # 1) chat_sessions unique constraint
    # -------------------------------------------------
    #
    # The `pg_constraint` existence check below is Postgres-only
    # catalog introspection. On sqlite (used by this project's own
    # migration test — see tests/test_migrations.py — and local dev)
    # there is no `pg_constraint` table at all, so this whole guarded
    # block is skipped and the constraint is created unconditionally
    # via `op.create_unique_constraint`, which alembic/SQLAlchemy
    # already know how to express for sqlite (via batch mode, see
    # `render_as_batch` in alembic/env.py).

    constraint_exists = (
        conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'uq_chat_sessions_store_conversation'"
            )
        ).first()
        if is_postgres
        else None
    )

    if not constraint_exists:

        duplicates = conn.execute(
            text(
                "SELECT store_id, conversation_key "
                "FROM chat_sessions "
                "GROUP BY store_id, conversation_key "
                "HAVING COUNT(*) > 1"
            )
        ).fetchall()

        if duplicates:
            raise RuntimeError(
                "Cannot add unique constraint "
                "uq_chat_sessions_store_conversation: "
                f"{len(duplicates)} duplicate "
                "(store_id, conversation_key) group(s) exist. "
                "Merge or remove the duplicate chat_sessions rows "
                "first (oldest row should win), then re-run this "
                "migration. This check exists to prevent silent "
                "data loss."
            )

        # `batch_alter_table` is required (not just `render_as_batch`
        # in alembic/env.py, which only affects autogenerate
        # rendering) for `create_unique_constraint` to actually run
        # on sqlite, which cannot ALTER an existing table to add a
        # constraint in place — batch mode does a copy-and-move
        # instead. On Postgres this still emits a plain ALTER TABLE
        # ADD CONSTRAINT, so behavior there is unchanged.
        with op.batch_alter_table("chat_sessions") as batch_op:
            batch_op.create_unique_constraint(
                "uq_chat_sessions_store_conversation",
                ["store_id", "conversation_key"],
            )

    # -------------------------------------------------
    # 2) pgvector upgrade (optional, Postgres-only)
    # -------------------------------------------------
    #
    # `pg_extension` is a Postgres system catalog and does not exist
    # on sqlite — skip this entire step there. sqlite never had a
    # `vector` column type to begin with, so knowledge_chunks.embedding
    # simply stays TEXT and semantic search stays disabled, exactly
    # like the "pgvector not installed" case below.

    pgvector_available = (
        conn.execute(
            text(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            )
        ).first()
        if is_postgres
        else None
    )

    if pgvector_available:

        column_is_vector = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' "
                "AND column_name = 'embedding' "
                "AND udt_name = 'vector'"
            )
        ).first()

        if not column_is_vector:

            # NULL embeddings survive the cast; a non-empty TEXT
            # value that is not valid vector syntax would abort
            # the migration loudly — never silently converted.
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
    # else: pgvector not installed on this database. The column
    # stays TEXT; semantic search remains disabled by the
    # application's vector_support probe. Nothing is destroyed.


def downgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    constraint_exists = (
        conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'uq_chat_sessions_store_conversation'"
            )
        ).first()
        if is_postgres
        else True
    )

    if constraint_exists:
        with op.batch_alter_table("chat_sessions") as batch_op:
            batch_op.drop_constraint(
                "uq_chat_sessions_store_conversation",
                type_="unique",
            )

    # The pgvector type change is intentionally NOT reversed:
    # converting vector -> text would be lossy in formatting and
    # the application handles both column types transparently.
