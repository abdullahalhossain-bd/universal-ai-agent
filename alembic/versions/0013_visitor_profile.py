"""add visitor profiles

Revision ID: 0013_visitor_profile
Revises: 0012_agent_auto_reply
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_visitor_profile"
down_revision = "0012_agent_auto_reply"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visitor_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("visitor_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "visitor_id", name="uq_visitor_profiles_store_visitor"),
    )
    op.create_index("ix_visitor_profiles_store_id", "visitor_profiles", ["store_id"])
    op.create_index("ix_visitor_profiles_visitor_id", "visitor_profiles", ["visitor_id"])


def downgrade() -> None:
    op.drop_index("ix_visitor_profiles_visitor_id", table_name="visitor_profiles")
    op.drop_index("ix_visitor_profiles_store_id", table_name="visitor_profiles")
    op.drop_table("visitor_profiles")
