"""
SQLAlchemy ORM models for website knowledge.

The active commerce architecture is Store-based.
Knowledge records therefore use store_id as the merchant scope.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Index,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


def _lazy_vector_type():
    """
    Use pgvector when available.

    Requires BOTH:
    - the `pgvector` Python package, and
    - the `vector` extension in the target database.

    If either is unavailable, fall back to Text so the
    keyword-search/ingestion path can still operate.

    Resolution is cached per process by
    `app.knowledge.vector_support`. When the database engine has not
    been probed yet, we probe it against the application engine.
    """

    from app.knowledge.vector_support import (
        resolve_vector_support,
        vector_support_enabled,
    )

    if not vector_support_enabled():
        try:
            from app.db.database import engine

            resolve_vector_support(engine)
        except Exception:
            return Text()

    if not vector_support_enabled():
        return Text()

    try:
        from pgvector.sqlalchemy import Vector

        return Vector(384)

    except ImportError:
        return Text()


class KnowledgePage(Base):

    __tablename__ = "knowledge_pages"

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

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    page_type: Mapped[str] = mapped_column(
        String(30),
        default="unknown",
        nullable=False,
    )

    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    http_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class KnowledgeChunk(Base):

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_embedding", "embedding"),
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

    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_pages.id"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    embedding = mapped_column(
        _lazy_vector_type(),
        nullable=True,
    )