"""Persist exhaustive per-row sync issue history.

Revision ID: 0029_sync_issues
Revises: 0028_merge_all_heads
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0029_sync_issues"
down_revision: Union[str, None] = "0028_merge_all_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    if "sync_issues" in sa.inspect(conn).get_table_names():
        return
    op.create_table(
        "sync_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.String(36), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("datasource_id", sa.String(36), sa.ForeignKey("datasources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("field", sa.String(80), nullable=False),
        sa.Column("issue_type", sa.String(80), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sync_issues_run_field", "sync_issues", ["run_id", "field", "id"])
    op.create_index("ix_sync_issues_datasource_created", "sync_issues", ["datasource_id", "created_at"])
    op.create_index("ix_sync_issues_product", "sync_issues", ["store_id", "product_id"])

def downgrade() -> None:
    op.drop_index("ix_sync_issues_product", table_name="sync_issues")
    op.drop_index("ix_sync_issues_datasource_created", table_name="sync_issues")
    op.drop_index("ix_sync_issues_run_field", table_name="sync_issues")
    op.drop_table("sync_issues")
