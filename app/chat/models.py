import secrets
import uuid

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class ChatSession(Base):

    __tablename__ = "chat_sessions"

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

    conversation_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    # Pseudonymous browser/customer identity. This is NOT an authentication
    # credential; customer conversation access is protected by access_token.
    visitor_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # High-entropy capability token used only by the public customer endpoints
    # for this conversation. Never expose it to merchant-side APIs.
    access_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
    )

    # Per-conversation control. "ai" is the default; "human" pauses AI.
    mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ai",
        server_default="ai",
    )

    # Who currently owns a human-mode conversation. This prevents a customer
    # from silently resuming AI after a merchant explicitly takes over.
    mode_owner: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ai",
        server_default="ai",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "conversation_key",
            name="uq_chat_sessions_store_conversation",
        ),
    )


class ChatMessage(Base):

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
