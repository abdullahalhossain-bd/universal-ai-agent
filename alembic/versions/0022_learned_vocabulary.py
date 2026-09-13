"""Add global (cross-store) learned_vocabulary cache.

Complements search_learnings (0018), which caches store-scoped product
name corrections. learned_vocabulary instead caches classifications of
generic filler/quantity words (e.g. "কয়ডা" = "koyta" = "how many") that
carry no store-specific meaning, so once ANY store's chatbot asks the
LLM about such a word, no store ever needs to ask again.

Revision ID: 0022_learned_vocabulary
Revises: 0021_merge_search_learning
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_learned_vocabulary"
down_revision: Union[str, None] = "0021_merge_search_learning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "learned_vocabulary" in inspector.get_table_names():
        return

    op.create_table(
        "learned_vocabulary",
        sa.Column("term", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("resolved_value", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("term"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "learned_vocabulary" not in sa.inspect(conn).get_table_names():
        return
    op.drop_table("learned_vocabulary")