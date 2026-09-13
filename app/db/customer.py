"""Store-scoped customer, identity, and identity-history records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("store_id", "customer_key", name="uq_customers_store_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    customer_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    merged_into_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CustomerIdentity(Base):
    __tablename__ = "customer_identities"
    __table_args__ = (
        UniqueConstraint("store_id", "identity_type", "identity_value", name="uq_customer_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    identity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    identity_value: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CustomerIdentityHistory(Base):
    __tablename__ = "customer_identity_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    identity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    identity_value: Mapped[str | None] = mapped_column(String(320), nullable=True)
    from_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    to_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class CustomerAuditLog(Base):
    __tablename__ = "customer_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
