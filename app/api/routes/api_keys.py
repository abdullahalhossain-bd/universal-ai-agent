"""
Merchant-facing API key management — list, create, revoke.

Store-scoped via app.core.tenant.get_current_store, which accepts
either the widget's x-api-key OR a dashboard session token, so these
work from the React dashboard (session) and, if someone prefers, a
scripted client (an existing api key managing its siblings).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import generate_api_key
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import APIKey, Store

router = APIRouter(prefix="/v1/stores/me/api-keys", tags=["api-keys"])


def _key_dict(key: APIKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "key_prefix": key.key_prefix,
        "created_at": key.created_at.isoformat(),
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "active": key.revoked_at is None,
    }


@router.get("")
def list_api_keys(
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    keys = (
        db.query(APIKey)
        .filter(APIKey.store_id == store.id)
        .order_by(APIKey.created_at.desc())
        .all()
    )
    return {"api_keys": [_key_dict(k) for k in keys]}


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(default="New Key", max_length=100)


@router.post("", status_code=201)
def create_api_key(
    payload: CreateAPIKeyRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    raw_key, prefix, key_hash = generate_api_key()
    key = APIKey(
        store_id=store.id,
        key_prefix=prefix,
        key_hash=key_hash,
        name=payload.name or "New Key",
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    # The raw key is returned exactly once, here — only the hash is
    # ever persisted (see app.core.security.hash_api_key). If the
    # merchant loses it, the only remedy is revoking this key and
    # creating a new one.
    return {**_key_dict(key), "api_key": raw_key}


@router.post("/{key_id}/revoke")
def revoke_api_key(
    key_id: str,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    key = (
        db.query(APIKey)
        .filter(APIKey.id == key_id, APIKey.store_id == store.id)
        .first()
    )
    if key is None:
        # 404, not 403 — never confirm whether a key_id from another
        # store exists at all.
        raise HTTPException(status_code=404, detail="API key not found")

    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        db.add(key)
        db.commit()
        db.refresh(key)

    return _key_dict(key)
