"""Add products.brand column.

Several call sites (app/chat/dynamic_service.py's product-match check,
app/responses/composer.py, app/products/sql_builder*.py) already
referenced Product.brand, but the column never existed on the table --
any code path that reached it raised AttributeError at runtime. This
migration adds the column and wires app/sync/normalize.py +
app/sync/upsert.py to populate it from merchant feeds going forward.

Revision ID: 0032_product_brand
Revises: 0031_billing_plans
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_product_brand"
down_revision: Union[str, None] = "0031_billing_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("products")}
    if "brand" not in columns:
        op.add_column("products", sa.Column("brand", sa.String(255), nullable=True))
        op.create_index("ix_products_brand", "products", ["brand"])


def downgrade() -> None:
    op.drop_index("ix_products_brand", table_name="products")
    op.drop_column("products", "brand")
