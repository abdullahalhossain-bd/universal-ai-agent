from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AgentConfig(Base):
    """Merchant-controlled AI assistant behavior for one store."""

    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Shop Assistant", server_default="Shop Assistant")
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, default="Hi! How can I help you today?", server_default="Hi! How can I help you today?")
    language: Mapped[str] = mapped_column(String(30), nullable=False, default="auto", server_default="auto")
    tone: Mapped[str] = mapped_column(String(30), nullable=False, default="friendly", server_default="friendly")
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    product_behavior: Mapped[str] = mapped_column(String(30), nullable=False, default="accurate", server_default="accurate")
    fallback_message: Mapped[str] = mapped_column(Text, nullable=False, default="I couldn't find that information. Please contact the store for help.", server_default="I couldn't find that information. Please contact the store for help.")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now())
