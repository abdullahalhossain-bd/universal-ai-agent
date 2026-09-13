"""Add fingerprint to persisted media health cache.

Revision ID: 0030_media_health_fingerprint
Revises: 0029_sync_issues
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0030_media_health_fingerprint"
down_revision: Union[str, None] = "0029_sync_issues"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("product_media_health")}
    if "source_fingerprint" not in columns:
        op.add_column("product_media_health", sa.Column("source_fingerprint", sa.String(64), nullable=True))
    if not any(i.get("name") == "ix_product_media_health_source_fingerprint" for i in inspector.get_indexes("product_media_health")):
        op.create_index("ix_product_media_health_source_fingerprint", "product_media_health", ["source_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_product_media_health_source_fingerprint", table_name="product_media_health")
    op.drop_column("product_media_health", "source_fingerprint")
