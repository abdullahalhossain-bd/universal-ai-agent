"""SyncRun lifecycle helpers.

A worker that crashes mid-sync (kill -9, OOM, node failure) leaves its
SyncRun stuck in ``running`` forever. The queue layer recovers the *job*
(XAUTOCLAIM after CLAIM_IDLE_MS), but nothing recovered the *run row*, so
PostgreSQL — the authoritative status source — kept reporting a sync that
had provably stopped.

The per-datasource lock in app.sync.worker guarantees at most one live
sync per datasource at any moment. Therefore, when a NEW run starts for a
datasource, any still-``running`` run for that same datasource is, by
construction, orphaned: its worker is gone. ``mark_superseded_runs``
closes those rows with an explanatory error instead of leaving them
stuck, keeping the status API honest for merchants.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import SyncRun

SUPERSEDED_NOTE = (
    "run superseded by a newer sync for this datasource "
    "(worker crashed or was restarted mid-sync)"
)


def mark_superseded_runs(db: Session, store_id: Optional[str], datasource_id: str) -> int:
    """Close stale ``running`` SyncRuns for a datasource when a new run starts.

    Returns the number of runs closed. Safe to call right before creating a
    new SyncRun: the datasource lock serializes legitimate syncs, so a
    still-running row at this point can only belong to a dead worker.
    """
    if not datasource_id:
        return 0
    query = db.query(SyncRun).filter(
        SyncRun.datasource_id == datasource_id,
        SyncRun.status == "running",
    )
    if store_id:
        query = query.filter(SyncRun.store_id == store_id)
    stale = query.all()
    now = datetime.utcnow()
    for run in stale:
        run.status = "error"
        run.finished_at = now
        run.error = SUPERSEDED_NOTE
        db.add(run)
    return len(stale)
