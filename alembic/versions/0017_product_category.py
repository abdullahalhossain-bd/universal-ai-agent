"""Add products.category column

REST/catalog-sync connectors already detect a product's category
(app/connectors/field_classifier.py, mapping.py) and normalize_product()
(app/catalog/normalizer.py) puts it in the normalized dict, but the
`products` table had no `category` column so `app/sync/upsert.py`
silently dropped it before it ever reached the database. This adds
the column so category survives the full sync -> DB path and can be
used as a search/filter field.

Revision ID: 0017_product_category
Revises: 0016_fix_agent_config_index
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_product_category"
down_revision: Union[str, None] = "0016_fix_agent_config_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    existing_columns = {
        col["name"]
        for col in sa.inspect(conn).get_columns("products")
    }

    if "category" in existing_columns:
        # Already present (e.g. re-run / already reconciled) —
        # nothing to do, avoids a duplicate-column error.
        return

    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("category", sa.String(255), nullable=True)
        )
        batch_op.create_index(
            "ix_products_category",
            ["category"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()

    existing_columns = {
        col["name"]
        for col in sa.inspect(conn).get_columns("products")
    }

    if "category" not in existing_columns:
        return

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_category")
        batch_op.drop_column("category")
