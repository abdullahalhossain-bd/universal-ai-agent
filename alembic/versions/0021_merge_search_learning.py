"""merge search learning branch into the production migration chain

Revision ID: 0021_merge_search_learning
Revises: 0020_session_version, 0018_search_learnings

The search-learning migration was introduced from the product-category
branch while the datasource/vector/session chain continued separately.
This explicit merge gives Alembic one deterministic head for
`alembic upgrade head`.
"""

from alembic import op

revision = "0021_merge_search_learning"
down_revision = ("0020_session_version", "0018_search_learnings")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
