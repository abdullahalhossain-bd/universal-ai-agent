"""remove redundant agent config index

Revision ID: 0016_fix_agent_config_index
Revises: 0015_merge_migration_heads
"""

from alembic import op

revision = "0016_fix_agent_config_index"
down_revision = "0015_merge_migration_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # store_id already has the canonical UNIQUE constraint. The old
    # migration also created a redundant non-unique index with the same
    # columns, which caused Alembic autogenerate drift against the model.
    op.drop_index("ix_agent_configs_store_id", table_name="agent_configs")


def downgrade() -> None:
    op.create_index(
        "ix_agent_configs_store_id",
        "agent_configs",
        ["store_id"],
        unique=False,
    )
