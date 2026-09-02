import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Numeric,
    Boolean,
    Integer,
    Index,
    func,
    true,
)
from sqlalchemy.types import JSON

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


# ---------------------------------
# Store
# ---------------------------------

class Store(Base):

    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    website_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ---------------------------------
    # Subscription / usage plan
    # ---------------------------------

    plan: Mapped[str] = mapped_column(
        String(20),
        default="starter",
        # Explicit DB-level default (not just the Python-side
        # `default=` above) so a row inserted by anything other than
        # this ORM (a raw SQL backfill, another service, a DBA
        # console) still gets a valid plan instead of violating
        # NOT NULL. Keeping both in sync is what `alembic check` /
        # tests/test_migrations.py verify.
        server_default="starter",
        nullable=False,
    )

    monthly_budget: Mapped[float] = mapped_column(
        Numeric(12, 6),
        default=1.000000,
        server_default="1.000000",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="setup",
        nullable=False,
    )

    # ---------------------------------
    # Billing (Stripe)
    # ---------------------------------
    # NULL until the store's first Checkout Session completes (see
    # app/billing/service.py). A store can exist and use the product
    # (on the free "starter" default budget) without ever having a
    # Stripe customer — these only get populated once real billing
    # starts.

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    # Mirrors Stripe's subscription.status ("active", "trialing",
    # "past_due", "canceled", ...) — kept in sync exclusively by the
    # webhook handler (app/billing/webhook.py), never written from a
    # user-facing request, since it must reflect what Stripe actually
    # charged, not what the merchant clicked.
    stripe_subscription_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # ---------------------------------
    # Platform-admin feature toggles ("packages")
    # ---------------------------------
    # Per-store on/off switches for the platform's AI capability
    # packages (see app.core.features.FEATURE_CATALOG for the fixed
    # set of keys, e.g. "ai_chat", "image_search"). Only ever written
    # by a platform admin via PATCH /v1/admin/stores/{id} — never by
    # the merchant themselves. Absence of a key (including the
    # common case of `{}` on every pre-existing store) means
    # "enabled" — see app.core.features.is_feature_enabled — so
    # rolling this out changes nothing about current stores until an
    # admin explicitly flips something off.
    enabled_features: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


# ---------------------------------
# User (dashboard login — separate from the widget's x-api-key auth)
# ---------------------------------

class User(Base):
    """
    A merchant's dashboard login. Deliberately simple: one user per
    store (no multi-user-per-store / roles yet — see
    app/api/routes/auth.py for the signup flow that creates both
    together). Authenticates with email + password
    (app.auth.password) and receives a JWT session
    (app.auth.jwt_session) — entirely separate from the `pk_live_...`
    API keys the storefront widget uses; a dashboard session must
    never be accepted anywhere the widget's x-api-key is expected,
    and vice versa.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


# ---------------------------------
# API Key
# ---------------------------------

class APIKey(Base):

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    store_id: Mapped[str] = mapped_column(
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    key_prefix: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    key_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        default="Default Key",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


# ---------------------------------
# Product
# ---------------------------------

class Product(Base):

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(
        "product_id",
        String(100),
        primary_key=True,
    )

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id"),
        primary_key=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        "product_name",
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    price: Mapped[float | None] = mapped_column(
        "selling_price",
        Numeric(12, 2),
        nullable=True,
    )

    stock: Mapped[float | None] = mapped_column(
        "quantity",
        Numeric(14, 3),
        nullable=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        "main_image",
        Text,
        nullable=True,
    )

    product_url: Mapped[str | None] = mapped_column(
        "product_url",
        Text,
        nullable=True,
    )

# ---------------------------------
# Merchant DataSource
# ---------------------------------


class DataSource(Base):
    """
    Persistent merchant product datasource configuration.

    store_id is the tenant boundary. connection_url may embed credentials;
    API responses must redact secrets (see app.datasources.redaction).
    """

    __tablename__ = "datasources"

    # Matches the composite index created in
    # alembic/versions/0005_datasources.py — declared here too so
    # `Base.metadata` (compared against the migration chain by
    # tests/test_migrations.py) doesn't drift from what's actually
    # migrated onto the database.
    __table_args__ = (
        Index("ix_datasources_store_active", "store_id", "active"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        # Matches alembic/versions/0005_datasources.py's
        # server_default="default" (see 0007_reconcile_schema_drift.py's
        # docstring for why the DB-level default actually gets applied
        # by 0007, not 0005 — 0001 already owns table creation).
        server_default="default",
    )

    connector_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    connection_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    api_base_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Opaque credential reference for future KMS/credential_store wiring.
    # When set, connection secrets are resolved at runtime rather than
    # embedded in connection_url. Currently optional.
    credential_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    table_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    mapping: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        # Matches alembic/versions/0005_datasources.py's
        # server_default=sa.true() — kept in sync so a raw-SQL
        # insert can't leave this NULL/false-by-accident, and so
        # `alembic check` doesn't flag a phantom drift.
        server_default=true(),
    )

    full_sync: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        # Matches 0005_datasources.py's server_default=sa.func.now().
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        server_default=func.now(),
    )

    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_sync_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    last_sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ---------------------------------
# Chat image (image-chat uploads)
# ---------------------------------


class ChatImage(Base):
    """
    A customer-uploaded photo used for image chat (vision-based
    product matching / visual Q&A).

    store_id is the tenant boundary — every lookup goes through
    `app.images.repository.ImageRepository`, which always filters by
    (store_id, id). `image_hash` is the sha256 of the raw bytes
    (see app.images.hashing) and is what `VisionCache` keys analysis
    results on, so re-uploading the same photo never re-pays for a
    vision-model call. `conversation_id` mirrors
    `ChatSession.conversation_key` (a client-supplied string, not a
    FK) since a photo can be uploaded before a chat session exists.
    """

    __tablename__ = "chat_images"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    user_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    storage_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    image_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        # Matches alembic/versions/0006_chat_images.py's
        # server_default=sa.func.now() — this was the one real
        # model/migration drift `alembic check` actually caught
        # (compare_server_default=True); every other created_at/
        # updated_at column in this file is corrected the same way.
        server_default=func.now(),
    )


# ---------------------------------
# Platform admin (Anthropic-us / operator login — separate from
# any merchant's dashboard User)
# ---------------------------------


class PlatformAdmin(Base):
    """
    Login for the *operator* of this whole platform (you), not a
    merchant. Deliberately its own table rather than a `User.role`
    flag: a platform admin has no `store_id` and must never be
    reachable through any store-scoped query, so keeping it a
    separate model makes "does this row belong to a tenant" a
    schema-level fact instead of something every query has to
    remember to check. Authenticates with email + password
    (app.auth.password, reused as-is) and receives its own JWT
    (app.auth.admin_session) whose `type` claim
    ("platform_admin_session") is disjoint from the merchant
    dashboard's ("dashboard_session") and the widget's `x-api-key` —
    none of the three credentials are ever interchangeable.

    There is no public signup route for this table on purpose;
    accounts are created with `scripts/create_platform_admin.py`
    (run from a trusted shell, e.g. `docker compose exec app ...`),
    the same way you'd create the first `root` DB user.
    """

    __tablename__ = "platform_admins"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        server_default=func.now(),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )