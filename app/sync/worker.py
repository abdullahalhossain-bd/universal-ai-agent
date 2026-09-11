"""Durable sync worker using Redis Streams consumer groups."""
from __future__ import annotations
import asyncio, logging, os, signal, uuid
from app.core.config import settings
from app.sync.processor import process_sync
from app.sync.queue import SyncQueue

logger = logging.getLogger("app.sync.worker")

async def run_worker(redis_url: str | None = None):
    queue = SyncQueue(redis_url or settings.redis_url)
    consumer = f"{os.uname().nodename}-{os.getpid()}"
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try: loop.add_signal_handler(sig, stopping.set)
        except NotImplementedError: pass
    logger.info("Sync worker started consumer=%s", consumer)
    try:
        while not stopping.is_set():
            await queue.promote_delayed()
            entries = await queue.claim_stale(consumer)
            if not entries: entries = await queue.read(consumer, count=1, block_ms=5000)
            for message_id, job, attempt in entries:
                if stopping.is_set(): break
                datasource_id = job.get("datasource_id")
                if not datasource_id:
                    await queue.ack(message_id); logger.error("sync job missing datasource_id message=%s", message_id); continue
                token = str(uuid.uuid4())
                if not await queue.acquire_lock(datasource_id, token):
                    logger.info("sync already running datasource=%s message=%s", datasource_id, message_id); continue
                heartbeat = None
                try:
                    async def renew():
                        while True:
                            await asyncio.sleep(60)
                            if not await queue.renew_lock(datasource_id, token): return
                    heartbeat = asyncio.create_task(renew())
                    if job.get("job_type") == "website_sync":
                        from app.crawler.web_ingestion import run_website_sync
                        result = await run_website_sync(job)
                    else:
                        result = await process_sync(job)
                    if result.errors:
                        outcome = await queue.requeue_or_dlq(message_id, job, attempt + 1, "; ".join(result.errors))
                        if outcome == "dead_letter": await queue.clear_enqueue_marker(datasource_id)
                        logger.warning("Sync failed datasource=%s attempt=%s outcome=%s errors=%s", datasource_id, attempt + 1, outcome, result.errors)
                    else:
                        await queue.ack(message_id); await queue.clear_enqueue_marker(datasource_id)
                        logger.info("Sync ok datasource=%s created=%s updated=%s", datasource_id, result.created, result.updated)
                except Exception as exc:
                    outcome = await queue.requeue_or_dlq(message_id, job, attempt + 1, str(exc))
                    if outcome == "dead_letter": await queue.clear_enqueue_marker(datasource_id)
                    logger.exception("Sync worker exception datasource=%s outcome=%s", datasource_id, outcome)
                finally:
                    if heartbeat: heartbeat.cancel()
                    await queue.release_lock(datasource_id, token)
    finally:
        await queue.close()
        logger.info("Sync worker stopped consumer=%s", consumer)

if __name__ == "__main__": asyncio.run(run_worker())
