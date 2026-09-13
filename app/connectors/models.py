from sqlalchemy import (
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class MerchantConnection(Base):

    __tablename__ = "merchant_connections"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
        nullable=False,
    )

    connector_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        default="default",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
    )
