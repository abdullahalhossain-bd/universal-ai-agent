import secrets
import uuid

from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    conversation_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    visitor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="ai", server_default="ai")
    mode_owner: Mapped[str] = mapped_column(String(20), nullable=False, default="ai", server_default="ai")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open", index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("store_id", "conversation_key", name="uq_chat_sessions_store_conversation"),
        UniqueConstraint("access_token", name="uq_chat_sessions_access_token"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
