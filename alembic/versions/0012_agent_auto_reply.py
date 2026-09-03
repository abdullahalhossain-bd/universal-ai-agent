"""add merchant auto reply control

Revision ID: 0012_agent_auto_reply
Revises: 0011_knowledge_embedding_index
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_agent_auto_reply"
down_revision = "0011_knowledge_embedding_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("auto_reply_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "auto_reply_enabled")
