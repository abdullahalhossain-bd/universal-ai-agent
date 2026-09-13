"""
Re-exports of auth-related SQLAlchemy models for backward compatibility.

The canonical APIKey ORM model lives in `app.db.models` to avoid duplicate
table definitions on the shared declarative Base. This module re-exports it
so that legacy imports of `from app.auth.models import APIKey` keep working.
"""

from app.db.models import (
    APIKey,
    Store,
)

__all__ = ["APIKey", "Store"]
