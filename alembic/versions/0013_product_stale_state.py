"""add safe stale product lifecycle fields

Revision ID: 0013_product_stale_state
Revises: 0012_sync_runs
"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0013_product_stale_state"
down_revision: Union[str, None] = "0012_sync_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("stale_since", sa.DateTime(), nullable=True))
    op.add_column("products", sa.Column("stale_misses", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("products", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.create_index("ix_products_datasource_stale", "products", ["source_datasource_id", "stale_since"])


def downgrade() -> None:
    op.drop_index("ix_products_datasource_stale", table_name="products")
    op.drop_column("products", "last_seen_at")
    op.drop_column("products", "is_active")
    op.drop_column("products", "stale_misses")
    op.drop_column("products", "stale_since")
