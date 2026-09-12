"""Backward-compatible re-exports for store/tenant resolution.

Prefer `app.core.tenant` for new code. These helpers stay so existing
imports keep working without drift.
"""

from fastapi import Depends

from app.auth.api_key import get_api_key
from app.core.tenant import (
    TenantContext,
    get_current_store,
    get_current_store_id,
    get_tenant_context,
)
from app.db.models import APIKey

__all__ = [
    "TenantContext",
    "get_current_store",
    "get_current_store_id",
    "get_tenant_context",
]


# Keep the historical async store-id helper for callers that imported it
# from this module. Implementation is shared with app.core.tenant.
async def get_current_store_id_async(
    api_key: APIKey = Depends(get_api_key),
) -> str:
    return api_key.store_id
