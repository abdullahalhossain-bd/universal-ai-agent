"""add persistent sync run history

Revision ID: 0012_sync_runs
Revises: 0011_knowledge_embedding_index
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_sync_runs"
down_revision: Union[str, None] = "0011_knowledge_embedding_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("datasource_id", sa.String(36), sa.ForeignKey("datasources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("sync_mode", sa.String(20), nullable=False, server_default="full"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("products_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stock_zeroed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("quality_report", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("reconciliation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_sync_runs_datasource_started", "sync_runs", ["datasource_id", "started_at"])
    op.create_index("ix_sync_runs_store_started", "sync_runs", ["store_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_runs_store_started", table_name="sync_runs")
    op.drop_index("ix_sync_runs_datasource_started", table_name="sync_runs")
    op.drop_table("sync_runs")
