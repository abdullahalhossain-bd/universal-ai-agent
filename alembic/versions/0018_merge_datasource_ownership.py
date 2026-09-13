"""merge datasource ownership migration with the main Alembic chain

Revision ID: 0018_merge_datasource_ownership
Revises: 0017_product_category, 0008_datasource_ownership
"""

from __future__ import annotations

from alembic import op

revision = "0018_merge_datasource_ownership"
down_revision = ("0017_product_category", "0008_datasource_ownership")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
