"""Add customer merge tombstone reference.

Revision ID: 0040_customer_merge_tombstone
Revises: 0039_customer_identity_history
"""

from alembic import op
import sqlalchemy as sa

revision = "0040_customer_merge_tombstone"
down_revision = "0039_customer_identity_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("merged_into_customer_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_customers_merged_into", "customers", "customers", ["merged_into_customer_id"], ["id"])
    op.create_index("ix_customers_merged_into_customer_id", "customers", ["merged_into_customer_id"])


def downgrade() -> None:
    op.drop_index("ix_customers_merged_into_customer_id", table_name="customers")
    op.drop_constraint("fk_customers_merged_into", "customers", type_="foreignkey")
    op.drop_column("customers", "merged_into_customer_id")
