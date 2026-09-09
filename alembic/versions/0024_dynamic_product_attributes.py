"""Add JSON storage for arbitrary merchant product attributes.

Revision ID: 0024_dynamic_product_attributes
Revises: 0023_query_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_dynamic_product_attributes"
down_revision: Union[str, None] = "0023_query_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("{}")),
    )


def downgrade() -> None:
    op.drop_column("products", "attributes")
