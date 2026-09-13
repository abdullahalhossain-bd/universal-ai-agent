"""Add missing behavioral_events.conversation_id index.

app/db/models.py's BehavioralEvent has declared conversation_id as
index=True since it was introduced (migration 0026), but no migration
ever actually created the index -- it silently existed only in the
model, so any real (Alembic-migrated) database has been doing full
table scans on this column. Confirmed via
tests/test_migrations.py::test_migrations_applied_match_current_models
(compare_metadata against a freshly-migrated schema).

Revision ID: 0033_behavioral_conv_index
Revises: 0032_product_brand
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_behavioral_conv_index"
down_revision: Union[str, None] = "0032_product_brand"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {ix["name"] for ix in inspector.get_indexes("behavioral_events")}
    if "ix_behavioral_events_conversation_id" not in existing:
        op.create_index(
            "ix_behavioral_events_conversation_id",
            "behavioral_events",
            ["conversation_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_behavioral_events_conversation_id", table_name="behavioral_events")
