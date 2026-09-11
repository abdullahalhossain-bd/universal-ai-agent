"""Add customer identity history for controlled linking and merges.

Revision ID: 0039_customer_identity_history
Revises: 0038_customer_entities
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_customer_identity_history"
down_revision = "0038_customer_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_identity_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("identity_type", sa.String(length=30), nullable=True),
        sa.Column("identity_value", sa.String(length=320), nullable=True),
        sa.Column("from_customer_id", sa.String(length=36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("to_customer_id", sa.String(length=36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customer_identity_history_store_id", "customer_identity_history", ["store_id"])
    op.create_index("ix_customer_identity_history_customer_id", "customer_identity_history", ["customer_id"])
    op.create_index("ix_customer_identity_history_from_customer_id", "customer_identity_history", ["from_customer_id"])
    op.create_index("ix_customer_identity_history_to_customer_id", "customer_identity_history", ["to_customer_id"])
    op.create_index("ix_customer_identity_history_created_at", "customer_identity_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_customer_identity_history_created_at", table_name="customer_identity_history")
    op.drop_index("ix_customer_identity_history_to_customer_id", table_name="customer_identity_history")
    op.drop_index("ix_customer_identity_history_from_customer_id", table_name="customer_identity_history")
    op.drop_index("ix_customer_identity_history_customer_id", table_name="customer_identity_history")
    op.drop_index("ix_customer_identity_history_store_id", table_name="customer_identity_history")
    op.drop_table("customer_identity_history")
