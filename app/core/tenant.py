"""
Store context + FastAPI dependency.

The active merchant identity is Store.
API keys are stored in api_keys.store_id.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.db.models import APIKey, Store


@dataclass
class TenantContext:
    """Backward-compatible Store context."""

    tenant_id: str
    api_key_id: str | None = None


async def get_current_store(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    authorization: str | None = Header(default=None),
) -> Store:
    """Resolve the active Store from a merchant JWT or public API key.

    When both credentials are present, the merchant Bearer JWT wins.
    This is important for dashboard requests: a stale/injected public API
    key must never cause the request to be resolved as a customer request
    and then trigger conversation-token authentication.
    """
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        if authorization:
            from app.auth.dashboard_auth import get_current_user

            user = await get_current_user(authorization=authorization, db=db)
            store = db.query(Store).filter(Store.id == user.store_id).first()
        elif x_api_key:
            api_key = await get_api_key(x_api_key=x_api_key, db=db)
            store = db.query(Store).filter(Store.id == api_key.store_id).first()
        else:
            raise HTTPException(status_code=401, detail="API key or session token required")

        if store is None:
            raise HTTPException(status_code=401, detail="Store not found")

        if store.status == "suspended":
            raise HTTPException(
                status_code=403,
                detail="This store has been suspended. Contact support.",
            )

        return store
    finally:
        db.close()


def get_current_store_id(
    api_key: APIKey = Depends(get_api_key),
) -> str:
    return api_key.store_id


def get_tenant_context(
    api_key: APIKey = Depends(get_api_key),
) -> TenantContext:
    return TenantContext(tenant_id=api_key.store_id, api_key_id=api_key.id)
