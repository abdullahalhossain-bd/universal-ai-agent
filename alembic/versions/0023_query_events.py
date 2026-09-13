"""Add query_events table for merchant-facing chat analytics.

Logs one row per customer chat query (intent, matched search term,
whether it returned results) so a merchant can see what their
customers are actually asking, which categories/products are in
demand, and which questions the bot is failing on ("knowledge gaps") —
see app/analytics/. Insertion is fire-and-forget from ChatService and
must never fail the chat response itself.

Revision ID: 0023_query_events
Revises: 0022_learned_vocabulary
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_query_events"
down_revision: Union[str, None] = "0022_learned_vocabulary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "query_events" in inspector.get_table_names():
        return

    op.create_table(
        "query_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("intent", sa.String(30), nullable=False),
        sa.Column("matched_term", sa.String(255), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("had_results", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_query_events_store_created",
        "query_events",
        ["store_id", "created_at"],
    )
    op.create_index(
        "ix_query_events_store_intent",
        "query_events",
        ["store_id", "intent"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "query_events" not in sa.inspect(conn).get_table_names():
        return
    op.drop_index("ix_query_events_store_intent", table_name="query_events")
    op.drop_index("ix_query_events_store_created", table_name="query_events")
    op.drop_table("query_events")