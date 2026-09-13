"""Add merchant-controlled widget branding.

Revision ID: 0034_widget_branding
Revises: 0033_behavioral_conv_index
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0034_widget_branding"
down_revision = "0033_behavioral_conv_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("logo_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "brand_color",
            sa.String(length=7),
            nullable=False,
            server_default="#111827",
        ),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "position",
            sa.String(length=20),
            nullable=False,
            server_default="bottom-right",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "position")
    op.drop_column("agent_configs", "brand_color")
    op.drop_column("agent_configs", "logo_url")
