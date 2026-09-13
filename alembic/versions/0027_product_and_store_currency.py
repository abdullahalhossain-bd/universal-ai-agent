"""Add currency to products and default_currency to stores.

Closes a gap where product price was always rendered with a hardcoded "$"
regardless of the merchant's actual currency. Product.currency holds the
per-product ISO code when the source data provides one; Store.default_currency
is the fallback used when it doesn't.

Revision ID: 0027_product_and_store_currency
Revises: 0026_behavioral_learning_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_product_and_store_currency"
down_revision: Union[str, None] = "0026_behavioral_learning_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column("default_currency", sa.String(10), nullable=False, server_default="USD"),
    )
    op.add_column(
        "products",
        sa.Column("currency", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "currency")
    op.drop_column("stores", "default_currency")
