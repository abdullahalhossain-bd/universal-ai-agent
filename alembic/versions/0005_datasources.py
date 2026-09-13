"""persistent merchant datasources

Revision ID: 0005_datasources
Revises: 0004_product_composite_pk

NOTE (added alongside 0007_reconcile_schema_drift): this migration
originally also contained an `op.create_table("datasources", ...)`
call, guarded by `if "datasources" not in inspector.get_table_names()`.
That guard was always False in practice: `0001_baseline_schema.py`
predates this migration being split out and already creates the same
table (without this file's `server_default=` values). In this chain's
linear history (0001 -> ... -> 0005) that `create_table` call could
never execute — the table always already exists by the time this
migration runs — so it has been removed entirely rather than kept as
unreachable dead code. This is a pure code-path removal with zero
effect on any already-migrated database (the branch never actually
ran anywhere, on any environment, ever), not a rewrite of DDL that
took effect. See
tests/test_migrations.py::test_no_migration_creates_a_table_owned_by_
an_earlier_migration, which guards against this class of bug
recurring (no table name may be created by `op.create_table` in more
than one migration file). The server-side defaults this migration was
*supposed* to establish (name/active/full_sync/created_at/updated_at)
are applied for real, idempotently, by
0007_reconcile_schema_drift.py; app/db/models.py's `DataSource`
columns declare matching `server_default=` so `alembic check` catches
any future drift of this kind.

For the same reason, `ix_datasources_store_id` (also created by
0001) is left out of the guarded index creation below — only
`ix_datasources_store_active`, which no earlier migration creates,
is genuinely new here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_datasources"
down_revision: Union[str, None] = "0004_product_composite_pk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # `datasources` itself is created by 0001_baseline_schema.py (see
    # this file's module docstring) and always already exists by the
    # time this migration runs. Only the composite index below is
    # this migration's actual, reachable contribution.
    existing_indexes = {
        idx["name"] for idx in inspector.get_indexes("datasources")
    } if "datasources" in inspector.get_table_names() else set()

    if "ix_datasources_store_active" not in existing_indexes:
        op.create_index(
            "ix_datasources_store_active",
            "datasources",
            ["store_id", "active"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "datasources" not in inspector.get_table_names():
        return

    existing_indexes = {
        idx["name"] for idx in inspector.get_indexes("datasources")
    }

    if "ix_datasources_store_active" in existing_indexes:
        op.drop_index("ix_datasources_store_active", table_name="datasources")

    # `datasources` itself and `ix_datasources_store_id` are owned by
    # 0001_baseline_schema.py (see this file's module docstring) —
    # its own downgrade() is what drops them.
