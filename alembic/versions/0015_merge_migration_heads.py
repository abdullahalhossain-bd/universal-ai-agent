"""merge the remaining Alembic migration heads

Revision ID: 0015_merge_migration_heads
Revises: 0014_admin_audit_logs, 91ef22d9dbc6
"""

from alembic import op

revision = "0015_merge_migration_heads"
down_revision = ("0014_admin_audit_logs", "91ef22d9dbc6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
