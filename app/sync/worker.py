"""Sync worker: dequeue jobs and run process_sync."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.sync.processor import process_sync
from app.sync.queue import SyncQueue

logger = logging.getLogger("app.sync.worker")


async def run_worker(redis_url: str | None = None):
    # Default to the same REDIS_URL the rest of the app uses,
    # rather than a hardcoded localhost — the worker normally runs
    # in its own container where localhost is not the Redis host.
    queue = SyncQueue(redis_url or settings.redis_url)
    logger.info("Sync worker started")

    while True:
        job = await queue.dequeue()
        if not job:
            continue

        try:
            logger.info("Processing job: %s", job.get("job_type", "product_sync"))
            result = await process_sync(job)
            if result.errors:
                logger.warning(
                    "Sync finished with errors store=%s errors=%s",
                    result.store_id,
                    result.errors,
                )
            else:
                logger.info(
                    "Sync ok store=%s created=%s updated=%s",
                    result.store_id,
                    result.created,
                    result.updated,
                )
        except Exception:
            logger.exception("Sync worker failed on job %s", job)


if __name__ == "__main__":
    asyncio.run(run_worker())
