"""Periodic enqueue for SQL and dynamic website datasources."""
from __future__ import annotations
import asyncio, logging
from typing import Any, Callable, Awaitable
from app.sync.queue import SyncQueue
logger=logging.getLogger("app.sync.scheduler")
GetDatasources=Callable[[],Awaitable[list[dict[str,Any]]]]

async def get_active_datasources() -> list[dict[str,Any]]:
    from app.db.database import SessionLocal
    from app.datasources.service import DataSourceService
    db=SessionLocal()
    try:
        rows=DataSourceService(db).list_active(); out=[]
        for ds in rows:
            if ds.connector_type=="website":
                out.append({"id":ds.id,"store_id":ds.store_id,"connector_type":"website","active":ds.active,"full_sync":ds.full_sync})
            elif ds.connector_type in {"postgresql","mysql","postgres"} and ds.table_name and ds.mapping and ds.connection_url:
                out.append({"id":ds.id,"store_id":ds.store_id,"connector_type":ds.connector_type,"table_name":ds.table_name,"active":ds.active,"full_sync":ds.full_sync})
        return out
    finally: db.close()

async def scheduler(redis_url: str="redis://localhost:6379",*,interval_seconds: int=15*60,get_datasources: GetDatasources|None=None):
    queue=SyncQueue(redis_url); fetch=get_datasources or get_active_datasources
    logger.info("Sync scheduler started (interval=%ss)",interval_seconds)
    while True:
        try:
            for ds in await fetch():
                if not ds.get("active",True): continue
                job={"store_id":ds.get("store_id") or ds.get("tenant_id"),"datasource_id":ds.get("id"),"job_type":"website_sync" if ds.get("connector_type")=="website" else "product_sync","full_sync":ds.get("full_sync",True)}
                await queue.enqueue(job)
                logger.info("enqueued %s store=%s datasource=%s",job["job_type"],job["store_id"],job["datasource_id"])
        except Exception: logger.exception("scheduler loop error")
        await asyncio.sleep(interval_seconds)

if __name__=="__main__": asyncio.run(scheduler())
