from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class BillingWebhookEvent(Base):
    """Durable idempotency ledger for verified Stripe webhook events."""
    __tablename__ = "billing_webhook_events"
    __table_args__ = (Index("ix_billing_webhook_events_store_id", "store_id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    store_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
