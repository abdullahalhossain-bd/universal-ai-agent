"""
Merchant datasource onboarding API.

All endpoints are store-scoped via the authenticated API key.
Secrets in connection_url are redacted in every response.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.tenant import get_current_store
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.datasources.redaction import public_datasource_dict, redact_url
from app.datasources.service import DataSourceService, SUPPORTED_SYNC_TYPES
from app.db.database import get_db
from app.db.models import Store
from app.sync.processor import process_sync

router = APIRouter(
    prefix="/v1/datasources",
    tags=["datasources"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateDataSourceRequest(BaseModel):
    name: str = "default"
    connector_type: str
    connection_url: str | None = None
    api_base_url: str | None = None
    table_name: str | None = None
    mapping: dict[str, Any] | None = None
    active: bool = True
    full_sync: bool = True
    skip_connection_test: bool = False


class UpdateDataSourceRequest(BaseModel):
    name: str | None = None
    connection_url: str | None = None
    api_base_url: str | None = None
    table_name: str | None = None
    mapping: dict[str, Any] | None = None
    active: bool | None = None
    full_sync: bool | None = None


class TestConnectionRequest(BaseModel):
    connector_type: str
    connection_url: str | None = None
    api_base_url: str | None = None


class DiscoverRequest(BaseModel):
    connection_url: str = Field(min_length=1)
    connector_type: str = "postgresql"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_datasource(
    payload: CreateDataSourceRequest,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    require_feature(store, FEATURE_DATABASE_SYNC)

    service = DataSourceService(db)
    try:
        ds = service.create(
            store.id,
            name=payload.name,
            connector_type=payload.connector_type,
            connection_url=payload.connection_url,
            api_base_url=payload.api_base_url,
            table_name=payload.table_name,
            mapping=payload.mapping,
            active=payload.active,
            full_sync=payload.full_sync,
            validate_connection=not payload.skip_connection_test,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return public_datasource_dict(ds)


@router.get("")
def list_datasources(
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    service = DataSourceService(db)
    items = service.list_for_store(store.id)
    return {
        "count": len(items),
        "items": [public_datasource_dict(ds) for ds in items],
    }


@router.get("/{datasource_id}")
def get_datasource(
    datasource_id: str,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    service = DataSourceService(db)
    ds = service.get(store.id, datasource_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="datasource not found")
    return public_datasource_dict(ds)


@router.patch("/{datasource_id}")
def update_datasource(
    datasource_id: str,
    payload: UpdateDataSourceRequest,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    service = DataSourceService(db)
    fields = payload.model_dump(exclude_unset=True)
    try:
        ds = service.update(store.id, datasource_id, **fields)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_datasource_dict(ds)


@router.delete("/{datasource_id}")
def delete_datasource(
    datasource_id: str,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    service = DataSourceService(db)
    ok = service.delete(store.id, datasource_id)
    if not ok:
        raise HTTPException(status_code=404, detail="datasource not found")
    return {"status": "deleted", "id": datasource_id}


@router.post("/test")
async def test_connection(
    payload: TestConnectionRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    # store dependency enforces auth; db unused but keeps signature consistent
    _ = store
    service = DataSourceService(db)
    connected = service.test_connection(
        payload.connector_type,
        connection_url=payload.connection_url,
        api_base_url=payload.api_base_url,
    )
    return {
        "connected": connected,
        "connector_type": payload.connector_type.lower(),
        "connection_url": redact_url(payload.connection_url),
    }


@router.post("/discover")
def discover_schema(
    payload: DiscoverRequest,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    _ = store
    ctype = payload.connector_type.lower()
    if ctype == "postgres":
        ctype = "postgresql"
    if ctype not in SUPPORTED_SYNC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="discovery supported only for postgresql/mysql",
        )

    service = DataSourceService(db)
    if not service.test_connection(ctype, payload.connection_url):
        raise HTTPException(status_code=400, detail="connection test failed")

    try:
        result = service.discover(payload.connection_url)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"discovery failed: {type(exc).__name__}",
        ) from exc

    result["connection_url"] = redact_url(payload.connection_url)
    return result


@router.post("/{datasource_id}/discover")
def discover_datasource(
    datasource_id: str,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    service = DataSourceService(db)
    ds = service.get(store.id, datasource_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="datasource not found")
    if not ds.connection_url:
        raise HTTPException(status_code=400, detail="no connection_url configured")
    if ds.connector_type not in SUPPORTED_SYNC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="discovery supported only for postgresql/mysql",
        )

    plaintext_url = DataSourceService.decrypt_connection_url(ds)
    try:
        result = service.discover(plaintext_url)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"discovery failed: {type(exc).__name__}",
        ) from exc

    result["datasource_id"] = ds.id
    result["connection_url"] = redact_url(plaintext_url)
    return result


@router.post("/{datasource_id}/sync")
async def trigger_sync(
    datasource_id: str,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    require_feature(store, FEATURE_DATABASE_SYNC)

    service = DataSourceService(db)
    ds = service.get(store.id, datasource_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="datasource not found")
    if not ds.active:
        raise HTTPException(status_code=400, detail="datasource is inactive")
    if ds.connector_type not in SUPPORTED_SYNC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="product sync not supported for this connector type",
        )
    if not ds.table_name or not ds.mapping:
        raise HTTPException(
            status_code=400,
            detail="table_name and mapping must be configured before sync",
        )
    if not ds.connection_url:
        raise HTTPException(status_code=400, detail="no connection_url configured")

    job = service.build_sync_job(ds)
    result = await process_sync(job)

    status = "success" if not result.errors else "error"
    error_msg = "; ".join(result.errors) if result.errors else None
    service.record_sync_result(
        store.id,
        ds.id,
        status=status,
        error=error_msg,
    )

    return {
        "datasource_id": ds.id,
        "store_id": store.id,
        "status": status,
        "result": result.to_dict(),
    }