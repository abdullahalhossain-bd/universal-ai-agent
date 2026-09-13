"""declare the knowledge embedding index in the active schema

Revision ID: 0011_knowledge_embedding_index
Revises: 0010_enabled_features
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_knowledge_embedding_index"
down_revision: Union[str, None] = "0010_enabled_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("knowledge_chunks")}
    if "ix_knowledge_chunks_embedding" not in indexes:
        op.create_index(
            "ix_knowledge_chunks_embedding",
            "knowledge_chunks",
            ["embedding"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("knowledge_chunks")}
    if "ix_knowledge_chunks_embedding" in indexes:
        op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
