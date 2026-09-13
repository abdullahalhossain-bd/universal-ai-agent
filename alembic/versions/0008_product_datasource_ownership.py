"""add product datasource ownership
Revision ID: 0008_datasource_ownership
Revises: 0007_reconcile_drift
"""
from alembic import op
import sqlalchemy as sa
revision="0008_datasource_ownership"
down_revision="0007_reconcile_drift"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    cols={c["name"] for c in inspector.get_columns("products")}
    if "source_datasource_id" not in cols:
        op.add_column("products",sa.Column("source_datasource_id",sa.String(36),nullable=True))
    indexes={i["name"] for i in sa.inspect(bind).get_indexes("products") if i.get("name")}
    if "ix_products_source_datasource_id" not in indexes:
        op.create_index("ix_products_source_datasource_id","products",["source_datasource_id"],unique=False)
    fks={fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("products")}
    if "fk_products_source_datasource_id_datasources" not in fks:
        op.create_foreign_key("fk_products_source_datasource_id_datasources","products","datasources",["source_datasource_id"],["id"],ondelete="SET NULL")

def downgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    fks={fk.get("name") for fk in inspector.get_foreign_keys("products")}
    if "fk_products_source_datasource_id_datasources" in fks: op.drop_constraint("fk_products_source_datasource_id_datasources","products",type_="foreignkey")
    indexes={i["name"] for i in sa.inspect(bind).get_indexes("products") if i.get("name")}
    if "ix_products_source_datasource_id" in indexes: op.drop_index("ix_products_source_datasource_id",table_name="products")
    cols={c["name"] for c in sa.inspect(bind).get_columns("products")}
    if "source_datasource_id" in cols: op.drop_column("products","source_datasource_id")
