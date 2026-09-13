"""platform admins

Adds `platform_admins` — the operator's own login, entirely separate
from `users` (merchant dashboard logins). See
app/db/models.py's PlatformAdmin docstring and
app/auth/admin_session.py for why the credential is kept disjoint
from both `users` and `api_keys`.

Revision ID: 0009_platform_admins
Revises: 91ef22d9dbc6
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_platform_admins"
down_revision: Union[str, None] = "91ef22d9dbc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "platform_admins" not in tables:
        op.create_table(
            "platform_admins",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_platform_admins_email"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "platform_admins" in tables:
        op.drop_table("platform_admins")