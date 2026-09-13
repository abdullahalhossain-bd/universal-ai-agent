from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

import redis.asyncio as redis

from app.core.config import settings
from app.core.features import FEATURE_DATABASE_SYNC, FEATURE_KNOWLEDGE_BASE, require_feature
from app.core.tenant import get_current_store
from app.datasources.redaction import public_datasource_dict
from app.datasources.service import DataSourceService
from app.db.database import get_db
from app.db.models import DataSource, Store, SyncRun
from app.knowledge.crawler import assert_safe_url
from app.sync.quality import normalize_http_url
from app.sync.queue import SyncQueue

router = APIRouter(prefix="/v1/websites", tags=["websites"])


class WebsiteCreate(BaseModel):
    # /v1/websites historically used `url`; accept `website_url` too so clients
    # can share the same request contract with /v1/knowledge/ingest.
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    website_url: str | None = Field(default=None, min_length=1, max_length=2048)
    name: str = Field(default="Website", min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_one_url(self):
        if not self.url and not self.website_url:
            raise ValueError("website URL is required")
        if self.url and self.website_url and self.url.strip() != self.website_url.strip():
            raise ValueError("provide only one website URL")
        return self

    @property
    def resolved_url(self) -> str:
        return (self.website_url or self.url or "").strip()


def _validation_error(message: str, field: str = "website_url") -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": "VALIDATION_ERROR", "message": message, "field": field},
    )


async def _queue_website(url: str, name: str, db: Session, store: Store, *, required_feature=FEATURE_DATABASE_SYNC):
    require_feature(store, required_feature)
    try:
        normalized = normalize_http_url(url)
        await assert_safe_url(normalized)
    except ValueError as exc:
        raise _validation_error(str(exc)) from exc

    service = DataSourceService(db)
    ds = db.query(DataSource).filter(
        DataSource.store_id == store.id,
        DataSource.connector_type == "website",
        DataSource.connection_url == normalized,
    ).first()
    created_here = False
    if ds is None:
        ds = service.create(
            store.id,
            name=name,
            connector_type="website",
            connection_url=normalized,
            full_sync=True,
            validate_connection=False,
        )
        created_here = True
    elif not ds.active:
        ds.active = True
        ds.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(ds)

    queue = SyncQueue(settings.redis_url)
    try:
        message_id = await queue.enqueue(service.build_sync_job(ds))
    except Exception as exc:
        if created_here:
            try:
                db.delete(ds)
                db.commit()
            except Exception:
                db.rollback()
        raise HTTPException(status_code=503, detail="Website ingestion queue is temporarily unavailable") from exc
    finally:
        await queue.close()
    return ds, message_id or "already_queued"


@router.post("")
async def add_website(payload: WebsiteCreate, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    try:
        ds, message_id = await _queue_website(payload.resolved_url, payload.name, db, store)
    except HTTPException:
        raise
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
    try:
        await assert_safe_url(normalize_http_url(ds.connection_url))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    queue = SyncQueue(settings.redis_url)
    try:
        message_id = await queue.enqueue(service.build_sync_job(ds))
    finally:
        await queue.close()
    return {"status": "queued", "datasource_id": datasource_id, "message_id": message_id or "already_queued"}


@router.get("/{datasource_id}/status")
async def website_status(datasource_id: str, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_KNOWLEDGE_BASE)
    ds = DataSourceService(db).get(store.id, datasource_id)
    if ds is None or ds.connector_type != "website":
        raise HTTPException(404, detail="website datasource not found")
    run = (
        db.query(SyncRun)
        .filter(SyncRun.store_id == store.id, SyncRun.datasource_id == datasource_id)
        .order_by(SyncRun.started_at.desc())
        .first()
    )
    r = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        progress = await r.hgetall(f"crawl_progress:{store.id}:{datasource_id}")
    finally:
        await r.aclose()
    return {
        "datasource": public_datasource_dict(ds),
        "crawl_progress": progress or None,
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
