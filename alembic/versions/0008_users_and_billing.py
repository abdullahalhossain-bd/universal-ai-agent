"""dashboard users + stripe billing columns

Adds:
* `users` — merchant dashboard login (email/password + JWT session,
  see app/auth/password.py, app/auth/jwt_session.py,
  app/api/routes/auth.py). Entirely separate from `api_keys`, which
  remains the widget/storefront's x-api-key credential.
* `stores.stripe_customer_id` / `stripe_subscription_id` /
  `stripe_subscription_status` — set exclusively by the Stripe
  webhook handler (app/billing/webhook.py), never by a user-facing
  request.

Revision ID: 0008_users_and_billing
Revises: 0007_reconcile_drift
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_users_and_billing"
down_revision: Union[str, None] = "0007_reconcile_drift"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("store_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_store_id", "users", ["store_id"], unique=False)

    if "stores" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("stores")}

        with op.batch_alter_table("stores") as batch_op:
            if "stripe_customer_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "stripe_customer_id", sa.String(length=255), nullable=True
                    )
                )
            if "stripe_subscription_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "stripe_subscription_id",
                        sa.String(length=255),
                        nullable=True,
                    )
                )
            if "stripe_subscription_status" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "stripe_subscription_status",
                        sa.String(length=30),
                        nullable=True,
                    )
                )

        existing_uqs = {
            uc["name"] for uc in sa.inspect(conn).get_unique_constraints("stores")
        } | {
            idx["name"]
            for idx in sa.inspect(conn).get_indexes("stores")
            if idx.get("unique")
        }

        if "uq_stores_stripe_customer_id" not in existing_uqs:
            with op.batch_alter_table("stores") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_stores_stripe_customer_id", ["stripe_customer_id"]
                )
        if "uq_stores_stripe_subscription_id" not in existing_uqs:
            with op.batch_alter_table("stores") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_stores_stripe_subscription_id", ["stripe_subscription_id"]
                )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "stores" in tables:
        existing_uqs = {
            uc["name"] for uc in inspector.get_unique_constraints("stores")
        }
        with op.batch_alter_table("stores") as batch_op:
            if "uq_stores_stripe_subscription_id" in existing_uqs:
                batch_op.drop_constraint(
                    "uq_stores_stripe_subscription_id", type_="unique"
                )
            if "uq_stores_stripe_customer_id" in existing_uqs:
                batch_op.drop_constraint(
                    "uq_stores_stripe_customer_id", type_="unique"
                )

        existing_cols = {c["name"] for c in inspector.get_columns("stores")}
        with op.batch_alter_table("stores") as batch_op:
            for col in (
                "stripe_subscription_status",
                "stripe_subscription_id",
                "stripe_customer_id",
            ):
                if col in existing_cols:
                    batch_op.drop_column(col)

    if "users" in tables:
        op.drop_table("users")
