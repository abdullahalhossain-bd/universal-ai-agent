"""Run a deterministic live website -> Redis worker -> Neon E2E check.

The caller must provide DATABASE_URL, REDIS_URL, and CREDENTIAL_ENCRYPTION_KEY
in the environment. The script never prints their values.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The crawler intentionally blocks private hosts unless this development-only
# switch is enabled. It is scoped to this short-lived deterministic fixture.
os.environ.setdefault("ALLOW_LOCAL_DATASOURCE_HOSTS", "true")
os.environ.setdefault("SYNC_WORKER_CONCURRENCY", "1")
os.environ.setdefault("SYNC_WORKER_POLL_MS", "500")
os.environ.setdefault("SYNC_WORKER_STATS_INTERVAL", "10")

from sqlalchemy import func

from app.api.routes.stores import CreateStoreRequest, create_store
from app.db.database import SessionLocal
from app.db.models import APIKey, DataSource, Product, Store, SyncRun
from app.chat.models import ChatMessage, ChatSession
from app.datasources.service import DataSourceService
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.sync.queue import GROUP, STREAM, SyncQueue


PRODUCT_HTML = """<!doctype html>
<html><head><title>Deterministic Test Catalog</title></head><body>
<h1>Deterministic Test Catalog</h1>
<p>Reliable product and support content for the live worker verification.</p>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "E2E Test Laptop",
  "sku": "E2E-LAPTOP-001",
  "description": "A deterministic product used by the local worker verification.",
  "category": "Computers",
  "brand": {"@type": "Brand", "name": "E2E Brand"},
  "offers": {"price": "1299.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}
}
</script>
</body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/robots.txt":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            body = b"User-agent: *\nAllow: /\n"
        elif self.path in {"/", "/catalog"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = PRODUCT_HTML.encode("utf-8")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            body = b"not found"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _wait_for(predicate, timeout: float = 90.0, interval: float = 1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def _pending_ids(redis_url: str):
    async def read_pending():
        queue = SyncQueue(redis_url)
        try:
            rows = await queue.redis.xpending_range(STREAM, GROUP, min="-", max="+", count=100)
        except Exception:
            return []
        finally:
            await queue.close()
        return {str(row.get("message_id") or row.get("message-id") or row[0]) for row in rows}

    return asyncio.run(read_pending())


def _enqueue(redis_url: str, job: dict) -> str:
    async def enqueue_once():
        queue = SyncQueue(redis_url)
        try:
            return await queue.enqueue(job)
        finally:
            await queue.close()

    return asyncio.run(enqueue_once())


def _cleanup_queue_namespace(redis_url: str):
    async def cleanup():
        queue = SyncQueue(redis_url)
        try:
            try:
                await queue.redis.xgroup_destroy(queue.stream, queue.group)
            except Exception:
                pass
            await queue.redis.delete(queue.stream, queue.dlq_stream, queue.delayed_key)
        finally:
            await queue.close()

    asyncio.run(cleanup())


def _cleanup(store_id: str, session_factory=None):
    db = (session_factory or SessionLocal)()
    try:
        datasource_ids = [row[0] for row in db.query(DataSource.id).filter(DataSource.store_id == store_id).all()]
        if datasource_ids:
            page_ids = [row[0] for row in db.query(KnowledgePage.id).filter(KnowledgePage.store_id == store_id).all()]
            if page_ids:
                db.query(KnowledgeChunk).filter(KnowledgeChunk.page_id.in_(page_ids)).delete(synchronize_session=False)
            db.query(KnowledgePage).filter(KnowledgePage.store_id == store_id).delete(synchronize_session=False)
            db.query(Product).filter(Product.store_id == store_id).delete(synchronize_session=False)
            db.query(SyncRun).filter(SyncRun.store_id == store_id).delete(synchronize_session=False)
            db.query(DataSource).filter(DataSource.store_id == store_id).delete(synchronize_session=False)
        db.query(APIKey).filter(APIKey.store_id == store_id).delete(synchronize_session=False)
        session_ids = [row[0] for row in db.query(ChatSession.id).filter(ChatSession.store_id == store_id).all()]
        if session_ids:
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.store_id == store_id).delete(synchronize_session=False)
        db.query(Store).filter(Store.id == store_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def main() -> int:
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{fixture.server_port}/"
    store_id = None
    datasource_id = None
    worker = None
    redis_url = os.environ["REDIS_URL"]
    worker_log = Path(tempfile.gettempdir()) / f"uaa-worker-{uuid.uuid4().hex}.log"
    try:
        db = SessionLocal()
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
        store_response = asyncio.run(
            create_store(
                request,
                CreateStoreRequest(name=f"Live E2E {uuid.uuid4().hex[:8]}", plan="starter"),
                db,
            )
        )
        store_id = store_response["store_id"]
        service = DataSourceService(db)
        datasource = service.create(
            store_id,
            name="Deterministic E2E Website",
            connector_type="website",
            connection_url=url,
            validate_connection=False,
        )
        datasource_id = datasource.id
        db.close()

        message_id = _enqueue(redis_url, service.build_sync_job(datasource))
        print(f"STORE_ID={store_id}")
        print(f"DATASOURCE_ID={datasource_id}")
        print(f"SYNC_RUN_ID= pending")
        print(f"QUEUE_ENTRY_ID={message_id}")

        with worker_log.open("w", encoding="utf-8") as log:
            worker = subprocess.Popen(
                [sys.executable, "-m", "app.sync.worker"],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                cwd=str(REPO_ROOT),
            )
        print("WORKER_STARTED=true")

        def current_run():
            session = SessionLocal()
            try:
                return session.query(SyncRun).filter(
                    SyncRun.store_id == store_id,
                    SyncRun.datasource_id == datasource_id,
                ).order_by(SyncRun.started_at.desc()).first()
            finally:
                session.close()

        run = _wait_for(current_run, timeout=120)
        if run is None:
            print("WORKER_CONSUMED=false")
            print("CRAWL_RESULT=timeout_waiting_for_sync_run")
            return 2
        print("WORKER_CONSUMED=true")
        print(f"SYNC_RUN_ID={run.id}")

        run = _wait_for(lambda: current_run() if (current_run() and current_run().finished_at) else None, timeout=180)
        if run is None:
            print("CRAWL_RESULT=timeout_waiting_for_completion")
            if worker_log.exists():
                print("WORKER_LOG_TAIL=" + " ".join(worker_log.read_text(encoding="utf-8", errors="replace")[-2000:].splitlines()))
            return 3
        session = SessionLocal()
        try:
            products = session.query(Product).filter(Product.store_id == store_id, Product.source_datasource_id == datasource_id).count()
            pages = session.query(KnowledgePage).filter(KnowledgePage.store_id == store_id).count()
            run = session.query(SyncRun).filter(SyncRun.id == run.id).one()
            status = run.status
            run_id = run.id
        finally:
            session.close()

        print(f"CRAWL_RESULT={status}")
        print(f"SYNC_STATUS={status}")
        print(f"PRODUCTS_CREATED={products}")
        print(f"KNOWLEDGE_PAGES_CREATED={pages}")
        pending = _pending_ids(redis_url)
        print(f"ACK_CONFIRMED={str(str(message_id) not in pending).lower()}")
        return 0 if status in {"success", "partial"} and str(message_id) not in pending else 4
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
        fixture.shutdown()
        if datasource_id and worker is not None and worker.returncode is not None:
            _cleanup(store_id)
        try:
            worker_log.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
