"""add missing knowledge_pages columns (content_hash, page_type, language, status)

Convergence migration. `Base.metadata.create_all()`-bootstrapped
databases and databases migrated with the pre-correction 0001
baseline lack four columns that the `KnowledgePage` ORM model
declares:

- content_hash  VARCHAR(64) NOT NULL  (deduplication key)
- page_type     VARCHAR(30) NOT NULL DEFAULT 'unknown'
- language      VARCHAR(10) NULL
- status        VARCHAR(20) NOT NULL DEFAULT 'active'

Existing rows receive backfilled defaults; no data is removed.
Column additions are guarded by inspecting the live schema rather
than `ADD COLUMN IF NOT EXISTS` (Postgres-only syntax — this now
also runs against sqlite, see tests/test_migrations.py), so
databases that already carry the columns are unaffected either way.

Revision ID: 0003_knowledge_page_columns
Revises: 0002_constraints
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_knowledge_page_columns"
down_revision: Union[str, None] = "0002_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = [
    ("content_hash", sa.Column("content_hash", sa.String(length=64), nullable=False, server_default="")),
    ("page_type", sa.Column("page_type", sa.String(length=30), nullable=False, server_default="unknown")),
    ("language", sa.Column("language", sa.String(length=10), nullable=True)),
    ("status", sa.Column("status", sa.String(length=20), nullable=False, server_default="active")),
]


def _existing_columns(conn) -> set[str]:
    inspector = sa.inspect(conn)
    return {col["name"] for col in inspector.get_columns("knowledge_pages")}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _existing_columns(conn)

    # Backfill order matters: the NOT NULL columns get server
    # defaults so existing rows remain valid after the ALTER.
    with op.batch_alter_table("knowledge_pages") as batch_op:
        for name, column in _NEW_COLUMNS:
            if name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    # Columns were added guarded by existence; drop them
    # symmetrically. Existing rows lose the derived metadata,
    # which is why downgrade is documented as lossy here.
    conn = op.get_bind()
    existing = _existing_columns(conn)

    with op.batch_alter_table("knowledge_pages") as batch_op:
        for name in ("status", "language", "page_type", "content_hash"):
            if name in existing:
                batch_op.drop_column(name)
