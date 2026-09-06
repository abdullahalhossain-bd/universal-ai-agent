"""Production API launcher with the Redis sync consumer in-process.

This keeps the API and queue consumer in one Render web service so the
application can run without a dedicated background-worker service.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from app.main import app
from app.sync.worker import run_worker

logger = logging.getLogger("app.runner")


async def _serve() -> None:
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=__import__("os").environ.get("PORT", "10000"),
        log_config=None,
    )
    server = uvicorn.Server(config)
    worker_task = asyncio.create_task(run_worker(), name="sync-worker")
    logger.info("In-process sync worker enabled")

    try:
        await server.serve()
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        logger.info("In-process sync worker stopped")


if __name__ == "__main__":
    asyncio.run(_serve())
