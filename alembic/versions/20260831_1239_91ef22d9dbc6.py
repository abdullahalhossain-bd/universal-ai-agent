"""fix chat images created at default

Revision ID: 91ef22d9dbc6
Revises: 0008_users_and_billing
Create Date: 2026-08-31 12:39:39.528291
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "91ef22d9dbc6"
down_revision: Union[str, None] = "0008_users_and_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("chat_images") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(),
                existing_nullable=False,
                server_default=sa.func.now(),
            )
    else:
        op.alter_column(
            "chat_images",
            "created_at",
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("chat_images") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(),
                existing_nullable=False,
                server_default=None,
            )
    else:
        op.alter_column(
            "chat_images",
            "created_at",
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
        )
