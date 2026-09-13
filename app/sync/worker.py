"""Durable sync worker using Redis Streams consumer groups."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid

from app.core.config import settings
from app.sync.processor import process_sync
from app.sync.queue import SyncQueue

logger = logging.getLogger("app.sync.worker")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except (TypeError, ValueError):
        return default


async def _dispatch_job(job: dict):
    """Route a dequeued job to its executor by job_type.

    Extracted from the worker loop so the routing itself (which
    executor handles which job_type) can be unit-tested without a
    real Redis stream. All executors share the same result contract:
    an object with `.errors`, `.data_quality` (with an optional
    "terminal" key), `.created`, and `.updated`.
    """
    job_type = job.get("job_type")
    if job_type == "website_sync":
        from app.crawler.web_ingestion import run_website_sync
        return await run_website_sync(job)
    if job_type == "knowledge_embeddings":
        from app.knowledge.embedding_service import run_embedding_backfill
        return await run_embedding_backfill(job)
    return await process_sync(job)


async def run_worker(redis_url: str | None = None):
    queue = SyncQueue(redis_url or settings.redis_url)
    consumer = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    concurrency = _bounded_int("SYNC_WORKER_CONCURRENCY", 4, 1, 32)
    poll_block_ms = _bounded_int("SYNC_WORKER_POLL_MS", 5000, 250, 30000)
    claim_count = _bounded_int("SYNC_WORKER_CLAIM_COUNT", concurrency, 1, 100)
    stats_interval = _bounded_int("SYNC_WORKER_STATS_INTERVAL", 60, 10, 3600)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stopping.set)
        except NotImplementedError:
            pass

    logger.info(
        "Sync worker started consumer=%s concurrency=%s poll_ms=%s",
        consumer,
        concurrency,
        poll_block_ms,
    )

    async def handle(message_id, job, attempt):
        datasource_id = job.get("datasource_id")
        if not datasource_id:
            await queue.ack(message_id)
            logger.error("sync job missing datasource_id message=%s", message_id)
            return

        token = str(uuid.uuid4())
        if not await queue.acquire_lock(datasource_id, token):
            # Another worker is syncing this datasource. Do not leave the
            # message pending for five minutes; defer it briefly and retry.
            await queue.defer_message(message_id, job, attempt, delay=2.0)
            logger.debug("sync deferred datasource=%s message=%s", datasource_id, message_id)
            return

        dispatch_task: asyncio.Task | None = None
        try:
            lock_lost = asyncio.Event()

            async def renew():
                while not stopping.is_set():
                    await asyncio.sleep(60)
                    if not await queue.renew_lock(datasource_id, token):
                        logger.warning("sync lock lost datasource=%s message=%s; aborting local execution", datasource_id, message_id)
                        lock_lost.set()
                        # A cancelled job leaves its message pending, so
                        # another consumer can reclaim it after
                        # CLAIM_IDLE_MS. Continuing to run without the lock
                        # would risk executing the same datasource
                        # concurrently with the worker that now holds it.
                        if dispatch_task is not None and not dispatch_task.done():
                            dispatch_task.cancel()
                        return

            heartbeat = asyncio.create_task(renew())

            dispatch_task = asyncio.create_task(_dispatch_job(job))
            result = await dispatch_task
            if lock_lost.is_set():
                # The work finished but the lock was lost mid-flight; the
                # message was left pending by the heartbeat path. Do not
                # ack or clear the enqueue marker: the reclaiming worker
                # owns this message now.
                logger.warning("sync finished after lock loss datasource=%s message=%s; leaving message pending", datasource_id, message_id)
                return

            if result.errors:
                if result.data_quality.get("terminal"):
                    await queue.ack(message_id)
                    await queue.clear_enqueue_marker(datasource_id)
                    logger.info(
                        "Sync skipped terminal datasource=%s message=%s reason=%s",
                        datasource_id,
                        message_id,
                        result.data_quality["terminal"],
                    )
                    return
                outcome = await queue.requeue_or_dlq(
                    message_id, job, attempt + 1, "; ".join(result.errors)
                )
                if outcome == "dead_letter":
                    await queue.clear_enqueue_marker(datasource_id)
                logger.warning(
                    "Sync failed datasource=%s attempt=%s outcome=%s errors=%s",
                    datasource_id,
                    attempt + 1,
                    outcome,
                    result.errors,
                )
            else:
                await queue.ack(message_id)
                await queue.clear_enqueue_marker(datasource_id)
                logger.info(
                    "Sync ok datasource=%s created=%s updated=%s",
                    datasource_id,
                    result.created,
                    result.updated,
                )
        except asyncio.CancelledError:
            # Leave the message pending so another consumer can reclaim it.
            logger.info("Sync task cancelled datasource=%s message=%s", datasource_id, message_id)
            raise
        except Exception as exc:
            outcome = await queue.requeue_or_dlq(message_id, job, attempt + 1, str(exc))
            if outcome == "dead_letter":
                await queue.clear_enqueue_marker(datasource_id)
            logger.exception(
                "Sync worker exception datasource=%s outcome=%s",
                datasource_id,
                outcome,
            )
        finally:
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            await queue.release_lock(datasource_id, token)

    async def log_stats():
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=stats_interval)
            except asyncio.TimeoutError:
                stats = await queue.stats()
                logger.info("Sync queue stats=%s", stats)

    stats_task = asyncio.create_task(log_stats())
    try:
        while not stopping.is_set():
            await queue.promote_delayed(limit=max(100, concurrency * 4))
            entries = await queue.claim_stale(consumer, count=claim_count)
            if not entries:
                entries = await queue.read(
                    consumer,
                    count=concurrency,
                    block_ms=poll_block_ms,
                )
            if entries:
                await asyncio.gather(*(handle(*entry) for entry in entries), return_exceptions=True)
    finally:
        stats_task.cancel()
        await asyncio.gather(stats_task, return_exceptions=True)
        # Do not cancel active handlers here: the current batch is awaited
        # before the loop can reach shutdown. Unfinished pending messages are
        # recoverable by XAUTOCLAIM after CLAIM_IDLE_MS.
        await queue.close()
        logger.info("Sync worker stopped consumer=%s", consumer)


if __name__ == "__main__":
    asyncio.run(run_worker())
