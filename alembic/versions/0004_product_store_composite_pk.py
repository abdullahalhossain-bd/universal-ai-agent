"""make product primary key tenant-safe

Revision ID: 0004_product_composite_pk
Revises: 0003_knowledge_page_columns
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "0004_product_composite_pk"
down_revision: Union[str, None] = "0003_knowledge_page_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _current_pk_name(conn) -> str | None:
    """
    Cross-dialect current primary-key constraint name for `products`.

    Uses `sqlalchemy.inspect` (works on sqlite, Postgres, MySQL...)
    instead of querying Postgres's `pg_constraint` catalog directly,
    which does not exist on sqlite (see tests/test_migrations.py,
    which runs every migration against a throwaway sqlite database).
    """
    inspector = sa.inspect(conn)
    pk = inspector.get_pk_constraint("products")
    return pk.get("name") if pk else None


def upgrade() -> None:
    conn = op.get_bind()

    duplicate = conn.execute(
        text(
            """
            SELECT product_id
            FROM products
            GROUP BY product_id
            HAVING COUNT(*) > 1
            """
        )
    ).first()

    if duplicate:
        raise RuntimeError(
            "Cannot change products primary key: "
            "duplicate product_id values exist across stores. "
            "Duplicates must be preserved by store and are "
            "expected to become valid under the composite key."
        )

    pk_name = _current_pk_name(conn)

    # Batch mode is required for sqlite (which cannot ALTER a
    # primary key in place) and is a no-op wrapper around plain
    # ALTER statements on Postgres.
    with op.batch_alter_table("products") as batch_op:
        if pk_name:
            batch_op.drop_constraint(pk_name, type_="primary")

        batch_op.create_primary_key(
            "products_pkey",
            ["product_id", "store_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    pk_name = _current_pk_name(conn)

    with op.batch_alter_table("products") as batch_op:
        if pk_name:
            batch_op.drop_constraint(pk_name, type_="primary")

        batch_op.create_primary_key(
            "products_pkey",
            ["product_id"],
        )
