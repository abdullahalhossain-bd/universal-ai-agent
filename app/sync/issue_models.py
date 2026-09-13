"""Durable per-row sync issues for exhaustive issue exploration."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class SyncIssue(Base):
    __tablename__ = "sync_issues"
    __table_args__ = (
        Index("ix_sync_issues_run_field", "run_id", "field", "id"),
        Index("ix_sync_issues_datasource_created", "datasource_id", "created_at"),
        Index("ix_sync_issues_product", "store_id", "product_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    datasource_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("datasources.id", ondelete="CASCADE"), nullable=True)
    field: Mapped[str] = mapped_column(String(80), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default="CURRENT_TIMESTAMP", nullable=False)
