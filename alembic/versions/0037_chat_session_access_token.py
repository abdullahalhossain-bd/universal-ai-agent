"""Add a private customer conversation capability token.

Revision ID: 0037_chat_session_access_token
Revises: 0036_chat_session_mode_owner
"""

from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa

revision = "0037_chat_session_access_token"
down_revision = "0036_chat_session_mode_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("access_token", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM chat_sessions WHERE access_token IS NULL")).fetchall()
    used = set()
    for row in rows:
        token = secrets.token_urlsafe(32)
        while token in used:
            token = secrets.token_urlsafe(32)
        used.add(token)
        bind.execute(
            sa.text("UPDATE chat_sessions SET access_token = :token WHERE id = :id"),
            {"token": token, "id": row[0]},
        )

    op.alter_column("chat_sessions", "access_token", nullable=False)
    op.create_unique_constraint("uq_chat_sessions_access_token", "chat_sessions", ["access_token"])
    op.create_index("ix_chat_sessions_access_token", "chat_sessions", ["access_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_access_token", table_name="chat_sessions")
    op.drop_constraint("uq_chat_sessions_access_token", "chat_sessions", type_="unique")
    op.drop_column("chat_sessions", "access_token")
