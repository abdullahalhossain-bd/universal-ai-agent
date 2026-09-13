"""add platform admin audit logs

Revision ID: 0014_admin_audit_logs
Revises: 0013_visitor_profile
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_admin_audit_logs"
down_revision = "0013_visitor_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("admin_id", sa.String(length=36), sa.ForeignKey("platform_admins.id"), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("store_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_audit_logs_admin_id", "admin_audit_logs", ["admin_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_store_id", "admin_audit_logs", ["store_id"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_store_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
