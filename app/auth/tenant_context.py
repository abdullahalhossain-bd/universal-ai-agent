from fastapi import Depends

from app.auth.api_key import get_api_key
from app.db.models import APIKey


async def get_current_store_id(
    api_key: APIKey = Depends(
        get_api_key
    ),
) -> str:

    return api_key.store_id


async def get_tenant_id(
    api_key: APIKey = Depends(
        get_api_key
    ),
) -> str:

    # Backward-compatible name.
    # Actual merchant identity is store_id.
    return api_key.store_id