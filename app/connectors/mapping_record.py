import uuid

from sqlalchemy import (
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class ConnectorMapping(Base):

    __tablename__ = (
        "connector_mappings"
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(
            uuid.uuid4()
        ),
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

    mapping_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
