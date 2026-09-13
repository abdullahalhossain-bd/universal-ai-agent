import uuid

from sqlalchemy import (
    String,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FieldMapping(Base):

    __tablename__ = "field_mappings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    table_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    column_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    semantic_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "semantic_type",
            "table_name",
            "column_name",
            name="uq_field_mapping",
        ),
    )
