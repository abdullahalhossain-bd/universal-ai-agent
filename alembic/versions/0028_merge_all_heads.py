"""Merge the remaining Alembic branches into one canonical head.

Revision ID: 0028_merge_all_heads
Revises: 0027_product_and_store_currency, 0016_sync_production_hardening
"""
from typing import Sequence, Union

revision: str = "0028_merge_all_heads"
down_revision: Union[str, tuple[str, str], None] = (
    "0027_product_and_store_currency",
    "0016_sync_production_hardening",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
