from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.tenant import get_current_store
from app.datasources.redaction import public_datasource_dict
from app.datasources.service import DataSourceService
from app.db.database import get_db
from app.db.models import Store, SyncRun
from app.sync.queue import SyncQueue

router = APIRouter(prefix="/v1/websites", tags=["websites"])


class WebsiteCreate(BaseModel):
    url: HttpUrl
    name: str = "Website"


@router.post("")
async def add_website(payload: WebsiteCreate, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    try:
        ds = DataSourceService(db).create(
            store.id,
            name=payload.name,
            connector_type="website",
            connection_url=str(payload.url),
            full_sync=True,
            validate_connection=False,
        )
        queue = SyncQueue(settings.redis_url)
        try:
            message_id = await queue.enqueue(DataSourceService(db).build_sync_job(ds))
        finally:
            await queue.close()
    except (ValueError, ConnectionError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"status": "queued", "datasource": public_datasource_dict(ds), "message_id": message_id}


@router.post("/{datasource_id}/resync")
async def resync_website(datasource_id: str, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    service = DataSourceService(db)
    ds = service.get(store.id, datasource_id)
    if ds is None or ds.connector_type != "website":
        raise HTTPException(404, detail="website datasource not found")
    queue = SyncQueue(settings.redis_url)
    try:
        message_id = await queue.enqueue(service.build_sync_job(ds))
    finally:
        await queue.close()
    return {"status": "queued", "datasource_id": datasource_id, "message_id": message_id}


@router.get("/{datasource_id}/status")
def website_status(datasource_id: str, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    ds = DataSourceService(db).get(store.id, datasource_id)
    if ds is None or ds.connector_type != "website":
        raise HTTPException(404, detail="website datasource not found")
    run = db.query(SyncRun).filter(SyncRun.store_id == store.id, SyncRun.datasource_id == datasource_id).order_by(SyncRun.started_at.desc()).first()
    return {
        "datasource": public_datasource_dict(ds),
        "last_run": None if run is None else {
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "products_seen": run.products_seen,
            "created": run.created,
            "updated": run.updated,
            "unchanged": run.unchanged,
            "quality_report": run.quality_report,
            "error": run.error,
        },
    }
