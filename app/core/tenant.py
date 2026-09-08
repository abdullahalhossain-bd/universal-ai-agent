"""
Store context + FastAPI dependency.

The active merchant identity is Store.
API keys are stored in api_keys.store_id.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.api_key import (
    get_api_key,
)

from app.db.models import (
    APIKey,
    Store,
)


@dataclass
class TenantContext:
    """
    Backward-compatible context object.

    The platform is Store-based, but existing AI
    components may still call the identifier tenant_id.
    """

    tenant_id: str
    api_key_id: str | None = None


async def get_current_store(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    authorization: str | None = Header(default=None),
) -> Store:
    """
    Resolves the authenticated Store from EITHER credential the
    platform issues:

    * `x-api-key: pk_live_...` — the storefront widget's credential
      (app.auth.api_key.get_api_key does the actual validation).
    * `Authorization: Bearer <jwt>` — a merchant's dashboard login
      session (app.auth.dashboard_auth.get_current_user).

    Both resolve to the same `Store`, so every route already gated on
    this dependency (datasources, discovery, mapping) is reachable
    from both the embeddable widget/API integrations *and* the React
    dashboard without special-casing each route. `x-api-key` is tried
    first only because it's the cheaper/older path; neither is more
    "trusted" than the other — both ultimately resolve to a store_id
    from a database row the caller proved they hold a real credential
    for.
    """

    # Lazy import avoids unnecessary circular imports.
    from app.db.database import (
        SessionLocal,
    )

    db = SessionLocal()

    try:
        if x_api_key:
            api_key = await get_api_key(x_api_key=x_api_key, db=db)
            store = (
                db.query(Store)
                .filter(Store.id == api_key.store_id)
                .first()
            )
        elif authorization:
            from app.auth.dashboard_auth import get_current_user

            user = await get_current_user(authorization=authorization, db=db)
            store = (
                db.query(Store)
                .filter(Store.id == user.store_id)
                .first()
            )
        else:
            raise HTTPException(
                status_code=401,
                detail="API key or session token required",
            )

        if store is None:
            raise HTTPException(
                status_code=401,
                detail="Store not found",
            )

        if store.status == "suspended":
            # The one enforcement point for both credential paths
            # (x-api-key and dashboard Bearer token) — a platform
            # admin suspending a store via PATCH /v1/admin/stores/{id}
            # (app/api/routes/admin.py) takes effect immediately for
            # every tenant-scoped route, the storefront widget, and
            # the merchant dashboard alike, without each of them
            # having to remember to check it themselves.
            raise HTTPException(
                status_code=403,
                detail="This store has been suspended. Contact support.",
            )

        return store

    finally:
        db.close()


def get_current_store_id(
    api_key: APIKey = Depends(
        get_api_key
    ),
) -> str:

    return api_key.store_id


def get_tenant_context(
    api_key: APIKey = Depends(
        get_api_key
    ),
) -> TenantContext:

    return TenantContext(
        tenant_id=api_key.store_id,
        api_key_id=api_key.id,
    )