"""Scalable sync-quality aggregation API.

Keeps the dashboard quality path bounded: counts are calculated in SQL,
media health is read from persisted verification rows, and no network checks
run inside a request.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Product, Store, SyncRun
from app.datasources.service import DataSourceService
from app.sync.media_models import ProductMediaHealth

router = APIRouter(prefix="/v1/datasources", tags=["datasources"])


def _count_status(query, column, value):
    return int(query.with_entities(func.coalesce(func.sum(case((column == value, 1), else_=0)), 0)).scalar() or 0)


@router.get("/{datasource_id}/quality", name="get_sync_quality_optimized")
def get_sync_quality_optimized(
    datasource_id: str,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    require_feature(store, FEATURE_DATABASE_SYNC)
    if DataSourceService(db).get(store.id, datasource_id) is None:
        raise HTTPException(404, detail="datasource not found")

    base = db.query(Product).filter(
        Product.store_id == store.id,
        Product.source_datasource_id == datasource_id,
        Product.is_active.is_(True),
    )
    total = int(base.with_entities(func.count(Product.id)).scalar() or 0)
    fields = {}
    for field in ("name", "price", "image_url", "product_url"):
        column = getattr(Product, field)
        present = int(base.with_entities(func.coalesce(func.sum(case((column.is_not(None) & (column != ""), 1), else_=0)), 0)).scalar() or 0)
        fields[field] = {
            "present": present,
            "missing": max(0, total - present),
            "coverage_percent": round(present / total * 100, 2) if total else 0.0,
        }

    latest = db.query(SyncRun).filter(
        SyncRun.store_id == store.id,
        SyncRun.datasource_id == datasource_id,
    ).order_by(SyncRun.started_at.desc()).first()
    report = (latest.quality_report if latest else {}) or {}
    dq = report.get("data_quality") or {}
    duplicates = dq.get("duplicates") or {}
    invalid = dq.get("invalid_data") or {}

    media_q = db.query(ProductMediaHealth).filter(
        ProductMediaHealth.store_id == store.id,
        ProductMediaHealth.source_datasource_id == datasource_id,
    )
    checked = int(media_q.with_entities(func.count(ProductMediaHealth.id)).scalar() or 0)
    media = {
        "products_checked": checked,
        "url": {k: _count_status(media_q, ProductMediaHealth.url_status, k) for k in ("missing", "valid", "broken")},
        "image": {k: _count_status(media_q, ProductMediaHealth.image_status, k) for k in ("missing", "valid", "broken")},
        "persisted": checked > 0,
        "verification_pending": checked == 0 and total > 0,
    }

    invalid_count = sum(dq.get("invalid_counts", {}).values()) if dq.get("invalid_counts") else sum(
        len(v) for v in invalid.values() if isinstance(v, list)
    )
    dup_penalty = min(10, duplicates.get("duplicate_id_count", 0) * .6 + duplicates.get("duplicate_sku_count", 0) * .4)
    broken = media["url"]["broken"] + media["image"]["broken"]
    base_score = (
        fields["name"]["coverage_percent"] * .30
        + fields["price"]["coverage_percent"] * .25
        + fields["image_url"]["coverage_percent"] * .20
        + fields["product_url"]["coverage_percent"] * .25
    )
    media_penalty = min(10, broken / total * 100 * .25) if total else 0
    skip_penalty = min(5, (latest.skipped if latest else 0) * .25)
    reconciliation = (latest.reconciliation if latest else {}) or {}
    rec_penalty = min(10, (reconciliation.get("unexplained", 0) or 0) / total * 10) if total and not reconciliation.get("reconciled", True) else 0
    health = max(0, min(100, round(base_score - min(12, invalid_count / max(1, total) * 100 * .20) - dup_penalty - media_penalty - skip_penalty - rec_penalty)))

    return {
        "datasource_id": datasource_id,
        "store_id": store.id,
        "products": total,
        "health_score": health,
        "rating": "Excellent" if health >= 90 else "Good" if health >= 75 else "Fair" if health >= 60 else "Poor",
        "fields": fields,
        "media_health": media,
        "duplicates": duplicates,
        "invalid_data": invalid,
        "latest_sync": {
            "id": latest.id,
            "status": latest.status,
            "sync_mode": latest.sync_mode,
            "created": latest.created,
            "updated": latest.updated,
            "unchanged": latest.unchanged,
            "skipped": latest.skipped,
            "stale": report.get("stale", {}),
            "price_changes": report.get("price_changes", {}),
            "stock_changes": report.get("stock_changes", {}),
            "schema_drift": report.get("schema_drift", {}),
            "repair_suggestions": report.get("repair_suggestions", []),
        } if latest else None,
    }
