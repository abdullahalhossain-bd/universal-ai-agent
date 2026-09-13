"""add revocable session versions

Revision ID: 0020_session_version
Revises: 0019_vector_embedding_guard
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0020_session_version"
down_revision: Union[str, None] = "0019_vector_embedding_guard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("platform_admins", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("platform_admins", "session_version")
    op.drop_column("users", "session_version")
