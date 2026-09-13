"""Exercise live website status lifecycle and PostgreSQL fallback."""
from __future__ import annotations

import json
import asyncio
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("ALLOW_LOCAL_DATASOURCE_HOSTS", "true")
os.environ.setdefault("RUN_SYNC_INLINE", "false")
os.environ.setdefault("CRAWLER_TIMEOUT_SECONDS", "1")
os.environ.setdefault("SYNC_QUEUE_NAMESPACE", f"e2e_status_{uuid.uuid4().hex}:")

from scripts.dev.live_website_worker_e2e import PRODUCT_HTML, _cleanup, _cleanup_queue_namespace, _wait_for
from app.api.routes.stores import CreateStoreRequest, create_store
from app.db.database import SessionLocal
from app.api.routes import stores as store_routes
from scripts.dev.live_db import SessionLocal as BoundedSessionLocal


class StatusFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/robots.txt":
            body, status, content_type = b"User-agent: *\nAllow: /\n", 200, "text/plain"
        elif self.path == "/":
            body, status, content_type = PRODUCT_HTML.encode(), 200, "text/html; charset=utf-8"
        elif self.path == "/timeout":
            time.sleep(5)
            body, status, content_type = PRODUCT_HTML.encode(), 200, "text/html; charset=utf-8"
        else:
            body, status, content_type = b"not found", 404, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def request(base, method, path, payload=None, api_key=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}


def start_api(env, port):
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_health(base):
    return _wait_for(lambda: request(base, "GET", "/health")[0] == 200, timeout=90, interval=1)


def main():
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), StatusFixtureHandler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    api = fallback_api = worker = None
    store_id = None
    try:
        env = os.environ.copy()
        env["RUN_SYNC_INLINE"] = "false"
        env["ALLOW_LOCAL_DATASOURCE_HOSTS"] = "true"
        env["CRAWLER_TIMEOUT_SECONDS"] = "1"
        api_port = 18100 + (os.getpid() % 500)
        base = f"http://127.0.0.1:{api_port}"
        api = start_api(env, api_port)
        if not wait_health(base):
            print("API_STARTED=false")
            return 2
        print("API_STARTED=true")
        async def allow_signup(**_kwargs):
            return {"limit": 5, "remaining": 5, "reset": 0}
        store_routes.enforce_signup_rate_limit = allow_signup
        db = BoundedSessionLocal()
        created = asyncio.run(create_store(
            SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={}),
            CreateStoreRequest(name=f"Status E2E {uuid.uuid4().hex[:8]}", plan="starter"),
            db,
        ))
        store_id = created["store_id"]
        api_key = created["api_key"]
        db.close()
        print(f"STORE_ID={store_id}")
        status, queued = request(base, "POST", "/v1/websites", {"url": f"http://127.0.0.1:{fixture.server_port}/", "name": "Status Success"}, api_key)
        datasource_id = queued["datasource"]["id"]
        print(f"DATASOURCE_ID={datasource_id}")
        print(f"QUEUED_STATUS={queued.get('status')}")

        worker = subprocess.Popen([sys.executable, "-m", "app.sync.worker"], cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        observed = []
        def read_success():
            code, body = request(base, "GET", f"/v1/websites/{datasource_id}/status", api_key=api_key)
            last = (body.get("last_run") or {}).get("status") if isinstance(body, dict) else None
            if last and last not in observed:
                observed.append(last)
            return body if last == "success" else None
        success_body = _wait_for(read_success, timeout=180, interval=.5)
        print(f"OBSERVED_SUCCESS_STATES={observed}")

        status, failed_queued = request(base, "POST", "/v1/websites", {"url": f"http://127.0.0.1:{fixture.server_port}/timeout", "name": "Status Failure"}, api_key)
        failed_id = failed_queued["datasource"]["id"]
        failed_states = []
        def read_failure():
            code, body = request(base, "GET", f"/v1/websites/{failed_id}/status", api_key=api_key)
            last = (body.get("last_run") or {}).get("status") if isinstance(body, dict) else None
            if last and last not in failed_states:
                failed_states.append(last)
            return body if last in {"error", "partial"} else None
        failure_body = _wait_for(read_failure, timeout=180, interval=.5)
        print(f"OBSERVED_FAILURE_STATES={failed_states}")
        print(f"FAILURE_TERMINAL_STATUS={(failed_states[-1] if failure_body and failed_states else None)}")

        fallback_port = api_port + 1
        fallback_env = env.copy()
        fallback_env["REDIS_URL"] = "redis://127.0.0.1:63999/0"
        fallback_api = start_api(fallback_env, fallback_port)
        fallback_base = f"http://127.0.0.1:{fallback_port}"
        fallback_ready = wait_health(fallback_base)
        fallback_code, fallback_body = request(fallback_base, "GET", f"/v1/websites/{datasource_id}/status", api_key=api_key) if fallback_ready else (0, {})
        fallback_status = (fallback_body.get("last_run") or {}).get("status") if isinstance(fallback_body, dict) else None
        print(f"POSTGRES_FALLBACK_STATUS={fallback_status}")
        print(f"POSTGRES_FALLBACK_HTTP={fallback_code}")
        return 0 if success_body and "success" in observed and failure_body and fallback_code == 200 and fallback_status == "success" else 4
    finally:
        for process in (worker, api, fallback_api):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        fixture.shutdown()
        if store_id:
            _cleanup(store_id, session_factory=BoundedSessionLocal)
        _cleanup_queue_namespace(os.environ["REDIS_URL"])


if __name__ == "__main__":
    raise SystemExit(main())
