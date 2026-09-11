"""Add per-conversation AI/human mode.

Revision ID: 0035_chat_session_mode
Revises: 0034_widget_branding
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0035_chat_session_mode"
down_revision = "0034_widget_branding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "mode",
            sa.String(length=20),
            nullable=False,
            server_default="ai",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "mode")
