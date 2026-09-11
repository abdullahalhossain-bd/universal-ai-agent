"""Add durable Stripe webhook idempotency ledger.

Revision ID: 0042_billing_webhook_idempotency
Revises: 0041_customer_inbox_lifecycle
"""

from alembic import op
import sqlalchemy as sa

revision = "0042_billing_webhook_idempotency"
down_revision = "0041_customer_inbox_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_billing_webhook_events_store_id", "billing_webhook_events", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_store_id", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
