"""Exhaustive, paginated sync issue history API."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import DataSource, Store
from app.sync.issue_models import SyncIssue

router = APIRouter(prefix="/v1/datasources", tags=["datasource-issues"])

@router.get("/{datasource_id}/issues-exhaustive")
def list_exhaustive_sync_issues(
    datasource_id: str,
    run_id: str | None = None,
    field: str | None = None,
    issue_type: str | None = None,
    product_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    require_feature(store, FEATURE_DATABASE_SYNC)
    ds = db.query(DataSource).filter(DataSource.id == datasource_id, DataSource.store_id == store.id).first()
    if ds is None:
        raise HTTPException(404, detail="datasource not found")
    q = db.query(SyncIssue).filter(
        SyncIssue.store_id == store.id,
        SyncIssue.datasource_id == datasource_id,
    )
    if run_id:
        q = q.filter(SyncIssue.run_id == run_id)
    if field:
        q = q.filter(SyncIssue.field == field.strip()[:80])
    if issue_type:
        q = q.filter(SyncIssue.issue_type == issue_type.strip()[:80])
    if product_id:
        q = q.filter(SyncIssue.product_id == product_id.strip()[:100])
    total = q.count()
    offset = (page - 1) * page_size
    items = q.order_by(SyncIssue.created_at.desc(), SyncIssue.id.desc()).offset(offset).limit(page_size).all()
    return {
        "datasource_id": datasource_id,
        "run_id": run_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size if total else 0,
        "items": [
            {
                "id": item.id,
                "run_id": item.run_id,
                "field": item.field,
                "issue_type": item.issue_type,
                "product_id": item.product_id,
                "value": item.value_text,
                "details": item.details,
                "created_at": item.created_at,
            }
            for item in items
        ],
    }
