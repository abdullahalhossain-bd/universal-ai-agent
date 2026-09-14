"""Deterministic real-worker restart/recovery verification."""
from __future__ import annotations

import asyncio
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

_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

os.environ.setdefault("SYNC_WORKER_CONCURRENCY", "1")
os.environ.setdefault("SYNC_WORKER_POLL_MS", "500")
os.environ.setdefault("SYNC_QUEUE_NAMESPACE", f"e2e_restart_{uuid.uuid4().hex}:")
os.environ.setdefault("SYNC_QUEUE_CLAIM_IDLE_MS", "3000")
os.environ.setdefault("SYNC_QUEUE_LOCK_TTL_MS", "5000")

PUBLIC_TEST_HOST = "public-example.test"
PUBLIC_TEST_IP = "93.184.216.34"

from app.api.routes.stores import CreateStoreRequest, create_store
from app.api.routes import stores as store_routes
from app.db.database import SessionLocal
from app.db.models import APIKey, DataSource, Product, Store, SyncRun
from app.datasources.service import DataSourceService
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.sync.queue import GROUP, STREAM, SyncQueue
from scripts.dev.live_website_worker_e2e import PRODUCT_HTML, _cleanup, _cleanup_queue_namespace, _wait_for
from scripts.dev.live_db import SessionLocal as BoundedSessionLocal


class SlowFixtureHandler(BaseHTTPRequestHandler):
    _root_requests = 0
    _root_lock = threading.Lock()

    def do_GET(self):  # noqa: N802
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
            status = 200
            content_type = "text/plain"
        elif self.path == "/":
            with self._root_lock:
                type(self)._root_requests += 1
                first_request = type(self)._root_requests == 1
            if first_request:
                time.sleep(20)
            body = PRODUCT_HTML.encode()
            status = 200
            content_type = "text/html; charset=utf-8"
        else:
            body = b"not found"
            status = 404
            content_type = "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _enqueue(redis_url, job):
    async def run():
        queue = SyncQueue(redis_url)
        try:
            return await queue.enqueue(job)
        finally:
            await queue.close()
    return asyncio.run(run())


def _pending(redis_url, message_id):
    async def run():
        queue = SyncQueue(redis_url)
        try:
            rows = await queue.redis.xpending_range(queue.stream, queue.group, min="-", max="+", count=100)
            return any(str(row.get("message_id") or row.get("message-id") or row[0]) == str(message_id) for row in rows)
        finally:
            await queue.close()
    return asyncio.run(run())


def _counts(store_id, datasource_id):
    db = BoundedSessionLocal()
    try:
        run = db.query(SyncRun).filter(SyncRun.store_id == store_id, SyncRun.datasource_id == datasource_id).order_by(SyncRun.started_at.desc()).first()
        products = db.query(Product).filter(Product.store_id == store_id, Product.source_datasource_id == datasource_id).count()
        pages = db.query(KnowledgePage).filter(KnowledgePage.store_id == store_id).count()
        return run, products, pages
    finally:
        db.close()


def _worker_env_with_public_fixture(test_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = f"{test_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = str(test_dir)
    return env


def _write_public_fixture_shim(test_dir: Path) -> Path:
    shim_path = test_dir / "sitecustomize.py"
    shim_path.write_text(
        """
import os
import socket
import sys

# sitecustomize runs during interpreter startup, BEFORE the `-m` runpy
# machinery puts the launch cwd on sys.path. The worker subprocess is
# launched with cwd=REPO_ROOT, so add it here first, otherwise
# `import app.knowledge.crawler` fails and this shim silently no-ops
# (which made the recovery fixture crawl fail DNS for the .test host).
_repo_root = os.getcwd()
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

_PUBLIC_HOST = "public-example.test"
_PUBLIC_IP = "127.0.0.1"


def _allow_public_url(url):
    return isinstance(url, str) and url.startswith(("http://public-example.test", "https://public-example.test"))


try:
    import app.knowledge.crawler as crawler

    _orig_is_private_host = crawler.is_private_host
    _orig_assert_safe_url = crawler.assert_safe_url

    def _patched_is_private_host(url):
        if _allow_public_url(url):
            return False
        return _orig_is_private_host(url)

    async def _patched_assert_safe_url(url):
        if _allow_public_url(url):
            return None
        return await _orig_assert_safe_url(url)

    class _LocalPublicResolver(crawler._PinnedResolver):
        async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
            if host == _PUBLIC_HOST:
                return [{
                    "hostname": host,
                    "host": _PUBLIC_IP,
                    "port": port,
                    "family": family,
                    "proto": socket.IPPROTO_TCP,
                    "flags": 0,
                }]
            return await super().resolve(host, port, family)

    crawler.is_private_host = _patched_is_private_host
    crawler.assert_safe_url = _patched_assert_safe_url
    crawler._PinnedResolver = _LocalPublicResolver
except Exception:
    import traceback
    traceback.print_exc()
""".strip() + "\n",
        encoding="utf-8",
    )
    return shim_path


def _wait_for_snapshot(store_id, datasource_id, timeout, interval=1.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = _counts(store_id, datasource_id)
        run, products, pages = last
        if run is not None:
            return last
        time.sleep(interval)
    return last


def _wait_for_finished(store_id, datasource_id, timeout, interval=1.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = _counts(store_id, datasource_id)
        run, products, pages = last
        if run is not None and run.finished_at is not None:
            return last
        time.sleep(interval)
    return last


def main():
    async def allow_signup(**_kwargs):
        return {"limit": 5, "remaining": 5, "reset": 0}

    store_routes.enforce_signup_rate_limit = allow_signup
    os.environ.setdefault("SYNC_WORKER_STATS_INTERVAL", "10")
    redis_url = os.environ["REDIS_URL"]
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), SlowFixtureHandler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    worker1 = worker2 = None
    worker2_stream = None
    store_id = datasource_id = None
    worker2_log = Path(tempfile.gettempdir()) / f"uaa-recovery-worker2-{uuid.uuid4().hex}.log"
    public_fixture_dir = Path(tempfile.mkdtemp(prefix="uaa-public-host-"))
    _write_public_fixture_shim(public_fixture_dir)
    try:
        db = BoundedSessionLocal()
        response = asyncio.run(create_store(
            SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={}),
            CreateStoreRequest(name=f"Restart E2E {uuid.uuid4().hex[:8]}", plan="starter"),
            db,
        ))
        store_id = response["store_id"]
        datasource = DataSourceService(db).create(
            store_id,
            name="Restart Recovery Website",
            connector_type="website",
            connection_url=f"http://{PUBLIC_TEST_HOST}:{fixture.server_port}/",
            validate_connection=False,
        )
        datasource_id = datasource.id
        job = DataSourceService(db).build_sync_job(datasource)
        db.close()
        message_id = _enqueue(redis_url, job)
        print(f"QUEUE_NAMESPACE={os.environ.get('SYNC_QUEUE_NAMESPACE')}")
        print(f"STORE_ID={store_id}")
        print(f"DATASOURCE_ID={datasource_id}")
        print(f"QUEUE_ENTRY_ID={message_id}")

        worker_env = _worker_env_with_public_fixture(public_fixture_dir)

        worker1 = subprocess.Popen([sys.executable, "-m", "app.sync.worker"], cwd=REPO_ROOT, env=worker_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("WORKER_1_STARTED=true")
        running = _wait_for_snapshot(store_id, datasource_id, timeout=60)
        if running is None or running[0] is None:
            print("WORKER_1_TERMINATED=false\nJOB_REMAINED_RECOVERABLE=false")
            return 2
        print(f"SYNC_RUN_ID={running[0].id}")
        worker1.kill()
        try:
            worker1.wait(timeout=20)
        except subprocess.TimeoutExpired:
            worker1.kill()
            worker1.wait(timeout=20)
        print("WORKER_1_TERMINATED=true")
        remained = _wait_for(lambda: _pending(redis_url, message_id), timeout=30)
        print(f"JOB_REMAINED_RECOVERABLE={str(bool(remained)).lower()}")
        if not remained:
            return 3

        stale_wait = 8
        print(f"STALE_WAIT_SECONDS={stale_wait}")
        time.sleep(stale_wait)
        worker2_stream = worker2_log.open("w", encoding="utf-8")
        worker2_env = _worker_env_with_public_fixture(public_fixture_dir)
        worker2 = subprocess.Popen([sys.executable, "-m", "app.sync.worker"], cwd=REPO_ROOT, env=worker2_env, stdout=worker2_stream, stderr=subprocess.STDOUT)
        print(f"WORKER_2_LOG_PATH={worker2_log}")
        print("WORKER_2_STARTED=true")
        reclaimed = _wait_for(lambda: _pending(redis_url, message_id), timeout=60)
        print(f"JOB_RECLAIMED={str(bool(reclaimed)).lower()}")
        completed = _wait_for_finished(store_id, datasource_id, timeout=240)
        if completed is None or completed[0] is None:
            print("JOB_RECOVERED=false")
            if worker2_log.exists():
                print("WORKER_2_LOG_TAIL=" + " ".join(worker2_log.read_text(encoding="utf-8", errors="replace")[-3000:].splitlines()))
            return 4
        run, products, pages = completed
        print("JOB_RECOVERED=true")
        print(f"SYNC_STATUS={run.status}")
        print(f"PRODUCTS_CREATED={products}")
        print(f"KNOWLEDGE_PAGES_CREATED={pages}")
        print(f"ACK_CONFIRMED={str(not _pending(redis_url, message_id)).lower()}")
        print(f"DUPLICATE_CHECK={str(products == 1 and pages == 1).upper()}")
        ack_confirmed = not _pending(redis_url, message_id)
        return 0 if run.status == "success" and products == 1 and pages == 1 and ack_confirmed else 5
    finally:
        for worker in (worker1, worker2):
            if worker is not None and worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
        if worker2_stream is not None:
            worker2_stream.close()
        fixture.shutdown()
        if store_id:
            _cleanup(store_id, session_factory=BoundedSessionLocal)
        _cleanup_queue_namespace(redis_url)
        try:
            for path in sorted(public_fixture_dir.glob("*"), reverse=True):
                if path.is_dir():
                    continue
                path.unlink(missing_ok=True)
            public_fixture_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
