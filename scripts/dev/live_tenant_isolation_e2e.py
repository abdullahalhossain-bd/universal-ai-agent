"""Live two-store API and service-layer tenant isolation verification."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("RUN_SYNC_INLINE", "false")
os.environ.setdefault("ALLOW_LOCAL_DATASOURCE_HOSTS", "true")
# This verification exercises keyword knowledge filtering. Avoid the optional
# pgvector probe during module import so Neon availability is tested by the
# bounded harness session rather than an unrelated model import side effect.
os.environ.setdefault("DISABLE_VECTOR_SUPPORT_PROBE", "true")

from app.api.routes.stores import CreateStoreRequest, create_store
from app.api.routes import stores as store_routes
from app.api.routes import datasources as datasource_routes
from app.api.routes import products as product_routes
from app.api.v1 import knowledge as knowledge_routes
from app.api.routes import messages as message_routes
from app.auth.api_key import get_api_key
from app.chat.service import ChatService
from app.db.database import SessionLocal
from app.db.models import DataSource, Product, Store, SyncRun
from app.datasources.service import DataSourceService
from app.knowledge.chunk import KnowledgePage
from scripts.dev.live_website_worker_e2e import _cleanup
from scripts.dev.live_db import SessionLocal as BoundedSessionLocal
from fastapi import HTTPException


def main() -> int:
    async def allow_signup(**_kwargs):
        return {"limit": 5, "remaining": 5, "reset": 0}

    store_routes.enforce_signup_rate_limit = allow_signup
    db = BoundedSessionLocal()
    store_ids = []
    try:
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
        first = __import__("asyncio").run(create_store(request, CreateStoreRequest(name=f"Tenant A {uuid.uuid4().hex[:8]}"), db))
        second = __import__("asyncio").run(create_store(request, CreateStoreRequest(name=f"Tenant B {uuid.uuid4().hex[:8]}"), db))
        store_a, store_b = first["store_id"], second["store_id"]
        store_ids = [store_a, store_b]
        ds_a = DataSourceService(db).create(store_a, name="A website", connector_type="website", connection_url="http://tenant-a.test/", validate_connection=False)
        ds_b = DataSourceService(db).create(store_b, name="B website", connector_type="website", connection_url="http://tenant-b.test/", validate_connection=False)
        ds_a_id, ds_b_id = ds_a.id, ds_b.id
        db.add_all([
            Product(id="TENANT-A-PRODUCT", store_id=store_a, source_datasource_id=ds_a.id, name="Store A Product", category="A Category", brand="A Brand", stock=4),
            Product(id="TENANT-B-PRODUCT", store_id=store_b, source_datasource_id=ds_b.id, name="Store B Product", category="B Category", brand="B Brand", stock=4),
            KnowledgePage(store_id=store_a, url="http://tenant-a.test/", title="A Knowledge", content="A private knowledge", content_hash="a"),
            KnowledgePage(store_id=store_b, url="http://tenant-b.test/", title="B Knowledge", content="B private knowledge", content_hash="b"),
            SyncRun(store_id=store_a, datasource_id=ds_a.id, status="success", sync_mode="website_full"),
            SyncRun(store_id=store_b, datasource_id=ds_b.id, status="success", sync_mode="website_full"),
        ])
        db.commit()
        session_a = ChatService(db)._get_or_create_session(store_id=store_a, conversation_id="tenant-conversation")
        session_b = ChatService(db)._get_or_create_session(store_id=store_b, conversation_id="tenant-conversation")
        session_a.access_token = "tenant-a-token"
        session_b.access_token = "tenant-b-token"
        db.commit()
        db.close()

        db = BoundedSessionLocal()
        key_a = __import__("asyncio").run(get_api_key(x_api_key=first["api_key"], db=db))
        key_b = __import__("asyncio").run(get_api_key(x_api_key=second["api_key"], db=db))
        store_obj_a = db.query(Store).filter(Store.id == store_a).first()
        store_obj_b = db.query(Store).filter(Store.id == store_b).first()
        aa = product_routes.search(q="Store", max_price=None, min_price=None, in_stock=None, limit=20, db=db, store=store_obj_a)
        bb = product_routes.search(q="Store", max_price=None, min_price=None, in_stock=None, limit=20, db=db, store=store_obj_b)
        try:
            a_to_b_ds = datasource_routes.get_datasource(ds_b_id, db=db, store=store_obj_a)
        except Exception:
            a_to_b_ds = None
        try:
            b_to_a_ds = datasource_routes.get_datasource(ds_a_id, db=db, store=store_obj_b)
        except Exception:
            b_to_a_ds = None
        a_to_b_knowledge = knowledge_routes.list_websites(store=store_obj_a, db=db)
        b_to_a_knowledge = knowledge_routes.list_websites(store=store_obj_b, db=db)
        try:
            a_to_b_runs = datasource_routes.list_sync_runs(ds_b_id, limit=20, offset=0, db=db, store=store_obj_a)
        except Exception:
            a_to_b_runs = {"count": 0}
        try:
            b_to_a_runs = datasource_routes.list_sync_runs(ds_a_id, limit=20, offset=0, db=db, store=store_obj_b)
        except Exception:
            b_to_a_runs = {"count": 0}
        try:
            a_to_b_conv = message_routes.customer_messages("tenant-conversation", x_api_key=first["api_key"], x_conversation_token="tenant-b-token", api_key=key_a, db=db)
            a_to_b_conv_blocked = False
        except HTTPException as exc:
            a_to_b_conv = {"messages": []}
            a_to_b_conv_blocked = exc.status_code in {401, 403}
        except Exception:
            a_to_b_conv = {"messages": ["unexpected-error"]}
            a_to_b_conv_blocked = False
        try:
            a_to_b_sync = __import__("asyncio").run(datasource_routes.trigger_sync(ds_b_id, db=db, store=store_obj_a))
            a_to_b_sync_blocked = False
        except HTTPException as exc:
            a_to_b_sync_blocked = exc.status_code in {403, 404}
        except Exception:
            a_to_b_sync_blocked = False
        try:
            a_to_b_status = __import__("asyncio").run(__import__("app.api.routes.websites", fromlist=["website_status"]).website_status(ds_b_id, db=db, store=store_obj_a))
            a_to_b_status_blocked = False
        except HTTPException as exc:
            a_to_b_status_blocked = exc.status_code in {403, 404}
        except Exception:
            a_to_b_status_blocked = False
        service_a = DataSourceService(db)
        service_b = DataSourceService(db)
        service_filter = service_a.get(store_a, ds_b_id) is None and service_b.get(store_b, ds_a_id) is None
        product_filter = db.query(Product).filter(Product.store_id == store_a, Product.id == "TENANT-B-PRODUCT").first() is None and db.query(Product).filter(Product.store_id == store_b, Product.id == "TENANT-A-PRODUCT").first() is None
        knowledge_filter = db.query(KnowledgePage).filter(KnowledgePage.store_id == store_a, KnowledgePage.title == "B Knowledge").first() is None and db.query(KnowledgePage).filter(KnowledgePage.store_id == store_b, KnowledgePage.title == "A Knowledge").first() is None
        run_filter = db.query(SyncRun).filter(SyncRun.store_id == store_a, SyncRun.datasource_id == ds_b_id).first() is None and db.query(SyncRun).filter(SyncRun.store_id == store_b, SyncRun.datasource_id == ds_a_id).first() is None
        db.close()
        print("A_TO_A=PASS" if aa.get("count") == 1 else "A_TO_A=FAIL")
        print("B_TO_B=PASS" if bb.get("count") == 1 else "B_TO_B=FAIL")
        blocked = a_to_b_ds is None and b_to_a_ds is None and a_to_b_runs["count"] == 0 and b_to_a_runs["count"] == 0 and not any("tenant-b.test" in item["domain"] for item in a_to_b_knowledge["websites"]) and not any("tenant-a.test" in item["domain"] for item in b_to_a_knowledge["websites"]) and a_to_b_conv_blocked and a_to_b_sync_blocked and a_to_b_status_blocked and service_filter and product_filter and knowledge_filter and run_filter
        print("A_TO_B=BLOCKED" if blocked else "A_TO_B=FAIL")
        print("B_TO_A=BLOCKED" if blocked else "B_TO_A=FAIL")
        return 0 if blocked and aa.get("count") == 1 and bb.get("count") == 1 else 4
    finally:
        db.close()
        for store_id in store_ids:
            _cleanup(store_id, session_factory=BoundedSessionLocal)


if __name__ == "__main__":
    raise SystemExit(main())
