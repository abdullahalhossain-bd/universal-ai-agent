"""add merchant AI agent configuration

Revision ID: 0012_agent_configs
Revises: 0011_knowledge_embedding_index
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_agent_configs"
down_revision: Union[str, None] = "0011_knowledge_embedding_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False, server_default="Shop Assistant"),
        sa.Column("welcome_message", sa.Text(), nullable=False, server_default="Hi! How can I help you today?"),
        sa.Column("language", sa.String(length=30), nullable=False, server_default="auto"),
        sa.Column("tone", sa.String(length=30), nullable=False, server_default="friendly"),
        sa.Column("system_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("product_behavior", sa.String(length=30), nullable=False, server_default="accurate"),
        sa.Column("fallback_message", sa.Text(), nullable=False, server_default="I couldn't find that information. Please contact the store for help."),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id"),
    )
    op.create_index("ix_agent_configs_store_id", "agent_configs", ["store_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_configs_store_id", table_name="agent_configs")
    op.drop_table("agent_configs")
