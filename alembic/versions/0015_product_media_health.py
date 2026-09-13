"""persist per-product URL/image health

Revision ID: 0015_product_media_health
Revises: 0014_product_source_fingerprint
"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0015_product_media_health"
down_revision: Union[str,None] = "0014_product_source_fingerprint"
branch_labels: Union[str,Sequence[str],None] = None
depends_on: Union[str,Sequence[str],None] = None

def upgrade() -> None:
    op.create_table("product_media_health",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("store_id",sa.String(36),sa.ForeignKey("stores.id",ondelete="CASCADE"),nullable=False),
        sa.Column("source_datasource_id",sa.String(36),sa.ForeignKey("datasources.id",ondelete="SET NULL"),nullable=True),
        sa.Column("product_id",sa.String(100),nullable=False),
        sa.Column("url_status",sa.String(20),nullable=False,server_default="missing"),
        sa.Column("image_status",sa.String(20),nullable=False,server_default="missing"),
        sa.Column("url_checked_at",sa.DateTime(),nullable=True),
        sa.Column("image_checked_at",sa.DateTime(),nullable=True),
    )
    op.create_index("ix_product_media_health_source_checked","product_media_health",["source_datasource_id","url_checked_at"])
    op.create_index("ix_product_media_health_store_product","product_media_health",["store_id","product_id"])

def downgrade() -> None:
    op.drop_index("ix_product_media_health_store_product",table_name="product_media_health")
    op.drop_index("ix_product_media_health_source_checked",table_name="product_media_health")
    op.drop_table("product_media_health")
