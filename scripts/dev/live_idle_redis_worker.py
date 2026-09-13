"""Verify real worker recovery after a five-minute idle Redis period."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("ALLOW_LOCAL_DATASOURCE_HOSTS", "true")
os.environ.setdefault("SYNC_WORKER_CONCURRENCY", "1")
os.environ.setdefault("SYNC_WORKER_POLL_MS", "30000")
os.environ.setdefault("SYNC_WORKER_STATS_INTERVAL", "30")
os.environ.setdefault("SYNC_QUEUE_NAMESPACE", f"e2e_idle_{uuid.uuid4().hex}:")

from app.api.routes.stores import CreateStoreRequest, create_store
from app.db.database import SessionLocal
from app.db.models import DataSource, Product, SyncRun
from app.datasources.service import DataSourceService
from app.knowledge.chunk import KnowledgePage
from app.sync.queue import SyncQueue
from scripts.dev.live_website_worker_e2e import FixtureHandler, _cleanup, _cleanup_queue_namespace, _enqueue, _wait_for


def main() -> int:
    redis_url = os.environ["REDIS_URL"]
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    worker = None
    store_id = datasource_id = None
    log_path = Path(os.environ.get("TEMP", ".")) / f"uaa-idle-worker-{uuid.uuid4().hex}.log"
    started = time.monotonic()
    try:
        db = SessionLocal()
        response = asyncio.run(create_store(
            SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={}),
            CreateStoreRequest(name=f"Idle Redis E2E {uuid.uuid4().hex[:8]}", plan="starter"),
            db,
        ))
        store_id = response["store_id"]
        datasource = DataSourceService(db).create(
            store_id,
            name="Idle Redis Website",
            connector_type="website",
            connection_url=f"http://127.0.0.1:{fixture.server_port}/",
            validate_connection=False,
        )
        datasource_id = datasource.id
        job = DataSourceService(db).build_sync_job(datasource)
        db.close()

        with log_path.open("w", encoding="utf-8") as log:
            worker = subprocess.Popen([sys.executable, "-m", "app.sync.worker"], cwd=REPO_ROOT, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
        print("WORKER_STARTED=true")
        idle_seconds = 305
        time.sleep(idle_seconds)
        print(f"IDLE_DURATION={int(time.monotonic() - started)}")

        async def stats_once():
            queue = SyncQueue(redis_url)
            try:
                return await queue.stats()
            finally:
                await queue.close()
        stats = asyncio.run(stats_once())
        print(f"STATS_AFTER_IDLE={stats}")
        message_id = _enqueue(redis_url, job)
        print("ENQUEUE_AFTER_IDLE=true")

        def completed_run():
            session = SessionLocal()
            try:
                return session.query(SyncRun).filter(SyncRun.store_id == store_id, SyncRun.datasource_id == datasource_id, SyncRun.finished_at.is_not(None)).order_by(SyncRun.started_at.desc()).first()
            finally:
                session.close()
        run = _wait_for(completed_run, timeout=240)
        session = SessionLocal()
        try:
            products = session.query(Product).filter(Product.store_id == store_id, Product.source_datasource_id == datasource_id).count()
            pages = session.query(KnowledgePage).filter(KnowledgePage.store_id == store_id).count()
        finally:
            session.close()
        async def acked():
            queue = SyncQueue(redis_url)
            try:
                pending = await queue.redis.xpending_range(queue.stream, queue.group, min="-", max="+", count=100)
                return not any(str(row.get("message_id") or row.get("message-id") or row[0]) == str(message_id) for row in pending)
            finally:
                await queue.close()
        ack = asyncio.run(acked())
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        lowered = log_text.lower()
        connection_errors = [term for term in ("winerror 121", "semaphore timeout", "connectionerror", "socket timeout", "xreadgroup timeout", "xpending failure") if term in lowered]
        print(f"WORKER_CONSUMED_AFTER_IDLE={str(run is not None).lower()}")
        print(f"ACK_AFTER_IDLE={str(ack).lower()}")
        print(f"WINERROR_121={str('winerror 121' in lowered).lower()}")
        print(f"CONNECTION_ERRORS={connection_errors}")
        return 0 if run is not None and run.status == "success" and products == 1 and pages == 1 and ack and not connection_errors else 4
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
        fixture.shutdown()
        if store_id:
            _cleanup(store_id)
        _cleanup_queue_namespace(redis_url)
        try:
            log_path.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
