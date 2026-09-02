"""add enabled_features to stores for feature flags

Adds per-store toggles for AI capability packages (see
app/core/features.FEATURE_CATALOG). Stores can individually enable/disable:
- ai_chat
- image_search
- knowledge_base
- database_sync

Absence of a key in the dict means "enabled by default" (backward
compatible).

Revision ID: 0010_enabled_features
Revises: 0009_platform_admins
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010_enabled_features"
down_revision: Union[str, None] = "0009_platform_admins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enabled_features column if it doesn't exist.
    # SQLite doesn't support "if not exists" on columns, so inspect.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = {col["name"] for col in inspector.get_columns("stores")}
    
    if "enabled_features" not in columns:
        op.add_column(
            "stores",
            sa.Column(
                "enabled_features",
                sa.JSON(),
                nullable=False,
                default=dict,
                server_default="{}",
            ),
        )

    indexes = {index["name"] for index in inspector.get_indexes("knowledge_chunks")}
    if "ix_knowledge_chunks_embedding" not in indexes:
        op.create_index(
            "ix_knowledge_chunks_embedding",
            "knowledge_chunks",
            ["embedding"],
        )


def downgrade() -> None:
    # On downgrade, drop the column if it exists.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = {col["name"] for col in inspector.get_columns("stores")}
    
    if "enabled_features" in columns:
        op.drop_column("stores", "enabled_features")

    indexes = {index["name"] for index in inspector.get_indexes("knowledge_chunks")}
    if "ix_knowledge_chunks_embedding" in indexes:
        op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
