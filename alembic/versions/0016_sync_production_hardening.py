"""sync production hardening

Revision ID: 0016_sync_production_hardening
Revises: 0015_product_media_health
"""
from __future__ import annotations
from typing import Sequence,Union
import sqlalchemy as sa
from alembic import op
revision: str = "0016_sync_production_hardening"
down_revision: Union[str,None] = "0015_product_media_health"
branch_labels: Union[str,Sequence[str],None] = None
depends_on: Union[str,Sequence[str],None] = None

def upgrade() -> None:
    op.create_index("uq_product_media_health_identity","product_media_health",["store_id","source_datasource_id","product_id"],unique=True)
    op.create_table(
        "schema_approval_audit",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("store_id",sa.String(36),sa.ForeignKey("stores.id",ondelete="CASCADE"),nullable=False),
        sa.Column("datasource_id",sa.String(36),sa.ForeignKey("datasources.id",ondelete="CASCADE"),nullable=False),
        sa.Column("action",sa.String(20),nullable=False),
        sa.Column("candidate_hash",sa.String(64),nullable=True),
        sa.Column("mapping",sa.JSON(),nullable=False,server_default="{}"),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.now()),
    )
    op.create_index("ix_schema_approval_audit_datasource_created","schema_approval_audit",["datasource_id","created_at"])

def downgrade() -> None:
    op.drop_index("ix_schema_approval_audit_datasource_created",table_name="schema_approval_audit")
    op.drop_table("schema_approval_audit")
    op.drop_index("uq_product_media_health_identity",table_name="product_media_health")
