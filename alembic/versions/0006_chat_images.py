"""chat_images table (image chat uploads)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_chat_images"
down_revision: Union[str, None] = "0005_datasources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names())

    if "chat_images" not in tables:
        op.create_table(
            "chat_images",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "store_id",
                sa.String(length=36),
                sa.ForeignKey("stores.id"),
                nullable=False,
            ),
            sa.Column(
                "conversation_id",
                sa.String(length=200),
                nullable=True,
            ),
            sa.Column(
                "user_id",
                sa.String(length=100),
                nullable=True,
            ),
            sa.Column(
                "storage_key",
                sa.Text(),
                nullable=False,
            ),
            sa.Column(
                "mime_type",
                sa.String(length=50),
                nullable=False,
            ),
            sa.Column(
                "size",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column(
                "image_hash",
                sa.String(length=64),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    existing_indexes = {
        idx["name"]
        for idx in inspector.get_indexes("chat_images")
        if idx.get("name")
    }

    if "ix_chat_images_store_id" not in existing_indexes:
        op.create_index(
            "ix_chat_images_store_id",
            "chat_images",
            ["store_id"],
        )

    if "ix_chat_images_conversation_id" not in existing_indexes:
        op.create_index(
            "ix_chat_images_conversation_id",
            "chat_images",
            ["conversation_id"],
        )

    if "ix_chat_images_image_hash" not in existing_indexes:
        op.create_index(
            "ix_chat_images_image_hash",
            "chat_images",
            ["image_hash"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names())

    if "chat_images" not in tables:
        return

    existing_indexes = {
        idx["name"]
        for idx in inspector.get_indexes("chat_images")
        if idx.get("name")
    }

    if "ix_chat_images_image_hash" in existing_indexes:
        op.drop_index(
            "ix_chat_images_image_hash",
            table_name="chat_images",
        )

    if "ix_chat_images_conversation_id" in existing_indexes:
        op.drop_index(
            "ix_chat_images_conversation_id",
            table_name="chat_images",
        )

    if "ix_chat_images_store_id" in existing_indexes:
        op.drop_index(
            "ix_chat_images_store_id",
            table_name="chat_images",
        )

    op.drop_table("chat_images")
