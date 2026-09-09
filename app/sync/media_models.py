"""Persistent per-product commerce media health."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class ProductMediaHealth(Base):
    __tablename__="product_media_health"
    __table_args__=(Index("ix_product_media_health_source_checked","source_datasource_id","checked_at"),Index("ix_product_media_health_store_product","store_id","product_id"))
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    store_id:Mapped[str]=mapped_column(String(36),ForeignKey("stores.id",ondelete="CASCADE"),nullable=False)
    source_datasource_id:Mapped[str|None]=mapped_column(String(36),ForeignKey("datasources.id",ondelete="SET NULL"),nullable=True)
    product_id:Mapped[str]=mapped_column(String(100),nullable=False)
    url_status:Mapped[str]=mapped_column(String(20),nullable=False,default="missing")
    image_status:Mapped[str]=mapped_column(String(20),nullable=False,default="missing")
    url_checked_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    image_checked_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
