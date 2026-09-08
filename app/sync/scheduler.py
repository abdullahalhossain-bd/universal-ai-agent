"""
Periodic sync job enqueue.

Loads active datasources from the database and enqueues canonical jobs.
Jobs carry datasource_id + store_id; process_sync loads connection details
from the DB so the Redis payload is not the sole secret channel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from app.sync.queue import SyncQueue

logger = logging.getLogger("app.sync.scheduler")

GetDatasources = Callable[[], Awaitable[list[dict[str, Any]]]]


async def get_active_datasources() -> list[dict[str, Any]]:
    """
    Load active datasources from the database.

    Returns dicts safe for enqueue (no need to embed passwords in logs;
    process_sync re-loads the full row by datasource_id).
    """
    from app.db.database import SessionLocal
    from app.datasources.service import DataSourceService

    db = SessionLocal()
    try:
        service = DataSourceService(db)
        rows = service.list_active()
        out = []
        for ds in rows:
            if ds.connector_type not in {"postgresql", "mysql", "postgres"}:
                continue
            if not ds.table_name or not ds.mapping:
                continue
            if not ds.connection_url:
                continue
            out.append(
                {
                    "id": ds.id,
                    "store_id": ds.store_id,
                    "connector_type": ds.connector_type,
                    "table_name": ds.table_name,
                    "active": ds.active,
                    "full_sync": ds.full_sync,
                    # connection_url intentionally omitted from the list
                    # log surface; process_sync loads it by id.
                }
            )
        return out
    finally:
        db.close()


async def scheduler(
    redis_url: str = "redis://localhost:6379",
    *,
    interval_seconds: int = 15 * 60,
    get_datasources: GetDatasources | None = None,
):
    queue = SyncQueue(redis_url)
    fetch = get_datasources or get_active_datasources

    logger.info("Sync scheduler started (interval=%ss)", interval_seconds)

    while True:
        try:
            datasources = await fetch()
            for ds in datasources:
                if not ds.get("active", True):
                    continue
                store_id = ds.get("store_id") or ds.get("tenant_id")
                job = {
                    "store_id": store_id,
                    "datasource_id": ds.get("id"),
                    "job_type": "product_sync",
                    # Optional overrides — process_sync loads the rest from DB
                    "full_sync": ds.get("full_sync", True),
                }
                await queue.enqueue(job)
                logger.info(
                    "enqueued product_sync store=%s datasource=%s",
                    store_id,
                    ds.get("id"),
                )
        except Exception:
            logger.exception("scheduler loop error")

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(scheduler())
