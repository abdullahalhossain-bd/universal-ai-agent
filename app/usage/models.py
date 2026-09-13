import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class UsageRecord(Base):

    __tablename__ = "usage_records"

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

    conversation_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
        nullable=False,
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        unique=True,
    )

    route: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    estimated_cost: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    cache_hit: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # ---------------------------------
    # Reservation lifecycle
    # ---------------------------------

    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        # Explicit DB-level default alongside the Python-side
        # `default=` — a row inserted outside the ORM (raw SQL,
        # another service) should never be able to violate NOT NULL
        # here. See the matching note on Store.plan.
        server_default="completed",
        nullable=False,
        index=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )