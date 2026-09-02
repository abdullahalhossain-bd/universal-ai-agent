from fastapi import (
    Depends,
    Header,
    HTTPException,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_api_key
from app.db.database import get_db
from app.db.models import APIKey, Store


async def authenticate_api_key(
    x_api_key: str | None = Header(
        default=None,
        alias="x-api-key",
    ),
    db: Session = Depends(get_db),
) -> APIKey:

    if not x_api_key:

        raise HTTPException(
            status_code=401,
            detail="API key required",
        )

    # Unify with `app.auth.api_key.get_api_key`: reject keys
    # that do not match the issued prefix BEFORE the hash
    # lookup, so both auth dependencies enforce identical
    # key-format rules.
    if not x_api_key.startswith("pk_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    key_hash = hash_api_key(
        x_api_key
    )

    result = db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.revoked_at.is_(None),
        )
    )

    api_key = (
        result.scalar_one_or_none()
    )

    if api_key is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
        )

    return api_key


def resolve_active_store(api_key: APIKey, db: Session) -> Store:
    """
    Shared by app.chat.router and app.api.routes.images — both
    deliberately authenticate with `authenticate_api_key` + a manual
    `Store` lookup rather than `app.core.tenant.get_current_store`
    (see their module docstrings), so this is the one place that
    lookup's suspended-store check lives for that family of routes,
    instead of being duplicated (and potentially forgotten) in each
    one. Mirrors `get_current_store`'s enforcement exactly: 401 if
    the store row is gone, 403 if a platform admin has suspended it.
    """
    store = db.query(Store).filter(Store.id == api_key.store_id).first()

    if store is None:
        raise HTTPException(status_code=401, detail="Store not found")

    if store.status == "suspended":
        raise HTTPException(
            status_code=403,
            detail="This store has been suspended. Contact support.",
        )

    return store