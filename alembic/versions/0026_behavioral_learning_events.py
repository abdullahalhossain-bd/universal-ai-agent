"""Add behavioral learning events for search feedback learning.

Revision ID: 0026_behavioral_learning_events
Revises: 0025_product_recommendation_signals
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_behavioral_learning_events"
down_revision: Union[str, None] = "0025_recommendation_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "behavioral_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("interaction_id", sa.String(36), nullable=False, index=True),
        sa.Column("store_id", sa.String(36), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("conversation_id", sa.String(200), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("query", sa.String(500), nullable=True),
        sa.Column("value", sa.Numeric(14, 4), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("{}")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_behavioral_events_store_created", "behavioral_events", ["store_id", "created_at"])
    op.create_index("ix_behavioral_events_store_product_created", "behavioral_events", ["store_id", "product_id", "created_at"])
    op.create_index("ix_behavioral_events_interaction", "behavioral_events", ["interaction_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_behavioral_events_interaction", table_name="behavioral_events")
    op.drop_index("ix_behavioral_events_store_product_created", table_name="behavioral_events")
    op.drop_index("ix_behavioral_events_store_created", table_name="behavioral_events")
    op.drop_table("behavioral_events")
