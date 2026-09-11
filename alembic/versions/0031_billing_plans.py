"""Add billing_plans table (DB-driven plan catalog).

Previously the plan catalog (starter/growth/pro, budgets, Stripe price
IDs) was a hardcoded dict in app/billing/plans.py. This migration moves
it into a real table so it can be managed via the admin API
(/v1/admin/plans) without a deploy.

Seeds the three existing plans with their current hardcoded budgets.
Stripe price IDs for growth/pro are seeded from the STRIPE_PRICE_GROWTH
/ STRIPE_PRICE_PRO environment variables if present at migration time
(preserving whatever was already configured), otherwise left NULL —
an operator can set them via the admin API afterwards.

Revision ID: 0031_billing_plans
Revises: 0030_media_health_fingerprint
"""

from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_billing_plans"
down_revision: Union[str, None] = "0030_media_health_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "billing_plans" not in inspector.get_table_names():
        op.create_table(
            "billing_plans",
            sa.Column("name", sa.String(20), primary_key=True),
            sa.Column("label", sa.String(50), nullable=False),
            sa.Column("monthly_budget", sa.Numeric(12, 6), nullable=False),
            sa.Column("stripe_price_id", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    billing_plans = sa.table(
        "billing_plans",
        sa.column("name", sa.String),
        sa.column("label", sa.String),
        sa.column("monthly_budget", sa.Numeric),
        sa.column("stripe_price_id", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    existing = {
        row[0]
        for row in conn.execute(sa.text("SELECT name FROM billing_plans")).fetchall()
    }

    seed_rows = [
        {
            "name": "starter",
            "label": "Starter",
            "monthly_budget": 1.00,
            "stripe_price_id": None,
            "is_active": True,
            "sort_order": 0,
        },
        {
            "name": "growth",
            "label": "Growth",
            "monthly_budget": 5.00,
            "stripe_price_id": os.environ.get("STRIPE_PRICE_GROWTH") or None,
            "is_active": True,
            "sort_order": 1,
        },
        {
            "name": "pro",
            "label": "Pro",
            "monthly_budget": 10.00,
            "stripe_price_id": os.environ.get("STRIPE_PRICE_PRO") or None,
            "is_active": True,
            "sort_order": 2,
        },
    ]

    rows_to_insert = [row for row in seed_rows if row["name"] not in existing]
    if rows_to_insert:
        op.bulk_insert(billing_plans, rows_to_insert)


def downgrade() -> None:
    op.drop_table("billing_plans")
