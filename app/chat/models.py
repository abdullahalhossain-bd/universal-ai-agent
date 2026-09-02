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


# ---------------------------------
# Chat session
# ---------------------------------
#
# One row per (store_id, conversation_key) — see the unique
# constraint below, which is what ChatService._get_or_create_session
# relies on to resolve a race between two concurrent first messages
# in the same conversation (app/chat/service.py catches the resulting
# IntegrityError and re-reads the winner instead of raising a 500).
# `conversation_key` is a client-supplied string, not a FK; it is
# also what `ChatImage.conversation_id` (app/db/models.py) mirrors so
# an uploaded photo can be linked before a session row exists.

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

    visitor_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
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


# ---------------------------------
# Chat message
# ---------------------------------
#
# `role` is one of "user" / "assistant" (real conversation turns,
# returned by history/context queries) or the internal sentinel
# "product_context" used by ChatService to persist the last shown
# product-search result set (for pagination / "আরেকটা দেখাও" and for
# resolving "এটা" references) — see _save_product_context /
# _load_product_context in app/chat/service.py. That sentinel row's
# `content` is a JSON blob, not user-facing text, which is why
# `_load_history` filters `role.in_(["user", "assistant"])`.

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
