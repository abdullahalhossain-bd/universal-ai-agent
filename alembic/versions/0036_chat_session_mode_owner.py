"""Track who owns AI/human conversation mode.

Revision ID: 0036_chat_session_mode_owner
Revises: 0035_chat_session_mode
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0036_chat_session_mode_owner"
down_revision = "0035_chat_session_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "mode_owner",
            sa.String(length=20),
            nullable=False,
            server_default="ai",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "mode_owner")
