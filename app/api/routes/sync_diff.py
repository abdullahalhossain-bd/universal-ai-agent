"""Run-to-run sync event diff API.

Uses durable SyncIssue events plus SyncRun counters, so the diff remains
available after the in-memory issue samples have been capped.
"""
from __future__ import annotations
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Store, SyncRun
from app.sync.issue_models import SyncIssue

router = APIRouter(prefix="/v1/datasources", tags=["datasources"])


def _run(db, store_id, datasource_id, run_id):
    return db.query(SyncRun).filter(
        SyncRun.id == run_id,
        SyncRun.store_id == store_id,
        SyncRun.datasource_id == datasource_id,
    ).first()


@router.get("/{datasource_id}/sync-diff")
def sync_diff(
    datasource_id: str,
    from_run: str = Query(..., min_length=1),
    to_run: str = Query(..., min_length=1),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    require_feature(store, FEATURE_DATABASE_SYNC)
    older = _run(db, store.id, datasource_id, from_run)
    newer = _run(db, store.id, datasource_id, to_run)
    if older is None or newer is None:
        raise HTTPException(404, detail="one or both sync runs not found")

    old_issues = db.query(SyncIssue).filter(SyncIssue.run_id == older.id).all()
    new_issues = db.query(SyncIssue).filter(SyncIssue.run_id == newer.id).all()
    old_keys = {(i.product_id, i.issue_type, i.field, i.value_text) for i in old_issues}
    new_keys = {(i.product_id, i.issue_type, i.field, i.value_text) for i in new_issues}
    added_keys = new_keys - old_keys
    resolved_keys = old_keys - new_keys

    def serialize(keys):
        result = []
        source = new_issues if keys is added_keys else old_issues
        for issue in source:
            key = (issue.product_id, issue.issue_type, issue.field, issue.value_text)
            if key in keys and len(result) < limit:
                result.append({"id": issue.id, "product_id": issue.product_id, "field": issue.field, "issue_type": issue.issue_type, "value": issue.value_text, "details": issue.details})
        return result

    old_types = Counter(i.issue_type for i in old_issues)
    new_types = Counter(i.issue_type for i in new_issues)
    issue_type_delta = {k: new_types.get(k, 0) - old_types.get(k, 0) for k in sorted(set(old_types) | set(new_types)) if new_types.get(k, 0) != old_types.get(k, 0)}
    return {
        "datasource_id": datasource_id,
        "from_run": {"id": older.id, "status": older.status, "created": older.created, "updated": older.updated, "unchanged": older.unchanged, "skipped": older.skipped},
        "to_run": {"id": newer.id, "status": newer.status, "created": newer.created, "updated": newer.updated, "unchanged": newer.unchanged, "skipped": newer.skipped},
        "counter_delta": {"created": newer.created - older.created, "updated": newer.updated - older.updated, "unchanged": newer.unchanged - older.unchanged, "skipped": newer.skipped - older.skipped, "stock_zeroed": newer.stock_zeroed - older.stock_zeroed},
        "issue_events": {"from_count": len(old_issues), "to_count": len(new_issues), "new": len(added_keys), "resolved": len(resolved_keys), "type_delta": issue_type_delta},
        "new_issue_events": serialize(added_keys),
        "resolved_issue_events": serialize(resolved_keys),
        "note": "Diff is based on durable sync events; unchanged products are not materialized as snapshots.",
    }
