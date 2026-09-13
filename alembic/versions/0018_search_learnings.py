"""Add persistent store-scoped search learning cache.

The chat product-search fallback may use Groq to correct a previously
unknown typo/query. Successful corrections are persisted so repeated
queries do not call the LLM again.

Revision ID: 0018_search_learnings
Revises: 0017_product_category
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_search_learnings"
down_revision: Union[str, None] = "0017_product_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "search_learnings" in inspector.get_table_names():
        return

    op.create_table(
        "search_learnings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False, server_default="product_correction"),
        sa.Column("source_query", sa.String(255), nullable=False),
        sa.Column("corrected_term", sa.String(255), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="groq"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_search_learnings_store_kind_query",
        "search_learnings",
        ["store_id", "kind", "source_query"],
        unique=True,
    )
    op.create_index(
        "ix_search_learnings_store",
        "search_learnings",
        ["store_id"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "search_learnings" not in sa.inspect(conn).get_table_names():
        return

    op.drop_index("ix_search_learnings_store", table_name="search_learnings")
    op.drop_index("uq_search_learnings_store_kind_query", table_name="search_learnings")
    op.drop_table("search_learnings")
