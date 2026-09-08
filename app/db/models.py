import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Numeric, Boolean, Integer, Index, func, true
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="starter", server_default="starter", nullable=False)
    monthly_budget: Mapped[float] = mapped_column(Numeric(12, 6), default=1.000000, server_default="1.000000", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="setup", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    stripe_subscription_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    enabled_features: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class APIKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(30), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), default="Default Key", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column("product_id", String(100), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), primary_key=True, index=True, nullable=False)
    source_datasource_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("datasources.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column("product_name", String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    price: Mapped[float | None] = mapped_column("selling_price", Numeric(12, 2), nullable=True)
    stock: Mapped[float | None] = mapped_column("quantity", Numeric(14, 3), nullable=True)
    image_url: Mapped[str | None] = mapped_column("main_image", Text, nullable=True)
    product_url: Mapped[str | None] = mapped_column("product_url", Text, nullable=True)

class DataSource(Base):
    __tablename__ = "datasources"
    __table_args__ = (Index("ix_datasources_store_active", "store_id", "active"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="default", server_default="default")
    connector_type: Mapped[str] = mapped_column(String(30), nullable=False)
    connection_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    full_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, server_default=func.now())
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

class ChatImage(Base):
    __tablename__ = "chat_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, server_default=func.now())

class PlatformAdmin(Base):
    __tablename__ = "platform_admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class SearchLearning(Base):
    __tablename__ = "search_learnings"
    __table_args__ = (
        Index("uq_search_learnings_store_kind_query", "store_id", "kind", "source_query", unique=True),
        Index("ix_search_learnings_store", "store_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="product_correction", server_default="product_correction")
    source_query: Mapped[str] = mapped_column(String(255), nullable=False)
    corrected_term: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="groq", server_default="groq")
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class LearnedVocabulary(Base):
    """Global (NOT store-scoped) cache of filler/quantity words the rule-based
    search planner/matcher couldn't classify and had to ask the LLM about.

    Deliberately not scoped by store_id: words like "কয়ডা" (how many) carry
    no store-specific meaning, so once any store's chatbot asks the LLM about
    such a word, no store ever needs to ask again. See app/search/learned_vocabulary.py.
    """
    __tablename__ = "learned_vocabulary"
    term: Mapped[str] = mapped_column(String(120), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    resolved_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())