"""persist deterministic source fingerprints

Revision ID: 0014_product_source_fingerprint
Revises: 0013_product_stale_state
"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0014_product_source_fingerprint"
down_revision: Union[str, None] = "0013_product_stale_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("products", sa.Column("source_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_products_source_fingerprint", "products", ["store_id", "source_datasource_id", "source_fingerprint"])

def downgrade() -> None:
    op.drop_index("ix_products_source_fingerprint", table_name="products")
    op.drop_column("products", "source_fingerprint")
