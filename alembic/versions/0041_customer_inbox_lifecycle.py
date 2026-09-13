"""Add customer privacy and inbox lifecycle fields.

Revision ID: 0041_customer_inbox_lifecycle
Revises: 0040_customer_merge_tombstone
"""

from alembic import op
import sqlalchemy as sa

revision = "0041_customer_inbox_lifecycle"
down_revision = "0040_customer_merge_tombstone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("anonymized_at", sa.DateTime(), nullable=True))
    op.add_column("chat_sessions", sa.Column("status", sa.String(length=20), nullable=False, server_default="open"))
    op.add_column("chat_sessions", sa.Column("read_at", sa.DateTime(), nullable=True))
    op.add_column("chat_sessions", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.create_index("ix_chat_sessions_status", "chat_sessions", ["status"])
    op.create_table(
        "customer_audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customer_audit_logs_store_id", "customer_audit_logs", ["store_id"])
    op.create_index("ix_customer_audit_logs_customer_id", "customer_audit_logs", ["customer_id"])
    op.create_index("ix_customer_audit_logs_conversation_id", "customer_audit_logs", ["conversation_id"])
    op.create_index("ix_customer_audit_logs_action", "customer_audit_logs", ["action"])
    op.create_index("ix_customer_audit_logs_created_at", "customer_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_customer_audit_logs_created_at", table_name="customer_audit_logs")
    op.drop_index("ix_customer_audit_logs_action", table_name="customer_audit_logs")
    op.drop_index("ix_customer_audit_logs_conversation_id", table_name="customer_audit_logs")
    op.drop_index("ix_customer_audit_logs_customer_id", table_name="customer_audit_logs")
    op.drop_index("ix_customer_audit_logs_store_id", table_name="customer_audit_logs")
    op.drop_table("customer_audit_logs")
    op.drop_index("ix_chat_sessions_status", table_name="chat_sessions")
    op.drop_column("chat_sessions", "archived_at")
    op.drop_column("chat_sessions", "read_at")
    op.drop_column("chat_sessions", "status")
    op.drop_column("customers", "anonymized_at")
