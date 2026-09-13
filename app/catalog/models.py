"""
Backward-compatible re-export of the canonical Product ORM model.

The canonical Product model lives in app.db.models so that the
shared SQLAlchemy Base has only one products table definition.
"""

from app.db.models import Product

__all__ = ["Product"]
