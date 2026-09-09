"""Add dedicated recommendation signals to products.

Revision ID: 0025_product_recommendation_signals
Revises: 0024_dynamic_product_attributes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_product_recommendation_signals"
down_revision: Union[str, None] = "0024_dynamic_product_attributes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("rating", sa.Numeric(3, 2), nullable=True))
    op.add_column("products", sa.Column("review_count", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("sales_count", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("bestseller_score", sa.Numeric(10, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "bestseller_score")
    op.drop_column("products", "sales_count")
    op.drop_column("products", "review_count")
    op.drop_column("products", "rating")
