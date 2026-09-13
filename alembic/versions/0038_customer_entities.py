"""Create first-class Customer and CustomerIdentity entities.

Revision ID: 0038_customer_entities
Revises: 0037_chat_session_access_token
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0038_customer_entities"
down_revision = "0037_chat_session_access_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "customer_key", name="uq_customers_store_key"),
    )
    op.create_index("ix_customers_store_id", "customers", ["store_id"])
    op.create_index("ix_customers_customer_key", "customers", ["customer_key"])
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_phone", "customers", ["phone"])

    op.create_table(
        "customer_identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("store_id", sa.String(length=36), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("identity_type", sa.String(length=30), nullable=False),
        sa.Column("identity_value", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "identity_type", "identity_value", name="uq_customer_identity"),
    )
    op.create_index("ix_customer_identities_store_id", "customer_identities", ["store_id"])
    op.create_index("ix_customer_identities_customer_id", "customer_identities", ["customer_id"])

    op.add_column("chat_sessions", sa.Column("customer_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_chat_sessions_customer_id", "chat_sessions", "customers", ["customer_id"], ["id"])
    op.create_index("ix_chat_sessions_customer_id", "chat_sessions", ["customer_id"])

    conn = op.get_bind()
    now = sa.func.now()
    profiles = conn.execute(sa.text("SELECT id, store_id, visitor_id, name, email, phone, created_at, updated_at FROM visitor_profiles")).mappings().all()
    for profile in profiles:
        customer_id = str(uuid.uuid4())
        customer_key = uuid.uuid4().hex
        created_at = profile["created_at"]
        updated_at = profile["updated_at"]
        conn.execute(sa.text("""
            INSERT INTO customers (id, store_id, customer_key, name, email, phone, first_seen_at, last_seen_at, created_at, updated_at)
            VALUES (:id, :store_id, :customer_key, :name, :email, :phone, :first_seen_at, :last_seen_at, :created_at, :updated_at)
        """), {"id": customer_id, "store_id": profile["store_id"], "customer_key": customer_key, "name": profile["name"], "email": profile["email"], "phone": profile["phone"], "first_seen_at": created_at, "last_seen_at": updated_at, "created_at": created_at, "updated_at": updated_at})
        conn.execute(sa.text("""
            INSERT INTO customer_identities (id, store_id, customer_id, identity_type, identity_value, created_at, updated_at)
            VALUES (:id, :store_id, :customer_id, 'browser', :identity_value, :created_at, :updated_at)
        """), {"id": str(uuid.uuid4()), "store_id": profile["store_id"], "customer_id": customer_id, "identity_value": profile["visitor_id"], "created_at": created_at, "updated_at": updated_at})
        conn.execute(sa.text("UPDATE chat_sessions SET customer_id = :customer_id WHERE store_id = :store_id AND visitor_id = :visitor_id"), {"customer_id": customer_id, "store_id": profile["store_id"], "visitor_id": profile["visitor_id"]})


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_customer_id", table_name="chat_sessions")
    op.drop_constraint("fk_chat_sessions_customer_id", "chat_sessions", type_="foreignkey")
    op.drop_column("chat_sessions", "customer_id")
    op.drop_index("ix_customer_identities_customer_id", table_name="customer_identities")
    op.drop_index("ix_customer_identities_store_id", table_name="customer_identities")
    op.drop_table("customer_identities")
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_index("ix_customers_customer_key", table_name="customers")
    op.drop_index("ix_customers_store_id", table_name="customers")
    op.drop_table("customers")
