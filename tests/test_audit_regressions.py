"""Regression tests for the 2026-09 production-readiness audit fixes.

Covers:
1. Orphaned SyncRun reaping (worker crash recovery at the DB level)
2. POST /v1/stores refuses to mint unauthenticated API keys in production
3. ALLOW_LOCAL_DATASOURCE_HOSTS refused in production settings
4. SSRF literal-host decimal/hex IPv4 encodings (was xfail gap)
5. OpenGraph product extraction (websites without JSON-LD)
6. /v1/images uses JWT-validating dashboard detection (same rule as /v1/chat)
7. Worker-crash recovery script contract (live; see also
   scripts/dev/live_worker_restart_recovery.py)
"""
from __future__ import annotations

import os

import pytest

# --- 1. Orphaned SyncRun reaping -----------------------------------------


def test_mark_superseded_runs_closes_stale_running_rows():
    from app.db.database import SessionLocal
    from app.db.models import DataSource, Store, SyncRun
    from app.sync.runs import mark_superseded_runs

    db = SessionLocal()
    store = None
    try:
        store = Store(name=f"reap-{os.urandom(4).hex()}", plan="starter")
        db.add(store)
        db.flush()
        ds1 = DataSource(store_id=store.id, name="ds1", connector_type="website", connection_url="https://example.com")
        ds2 = DataSource(store_id=store.id, name="ds2", connector_type="website", connection_url="https://example.org")
        db.add_all([ds1, ds2])
        db.flush()
        orphan = SyncRun(store_id=store.id, datasource_id=ds1.id, status="running", sync_mode="full")
        done = SyncRun(store_id=store.id, datasource_id=ds2.id, status="success", sync_mode="full")
        db.add_all([orphan, done])
        db.commit()

        closed = mark_superseded_runs(db, store.id, ds1.id)
        db.commit()

        assert closed == 1
        db.refresh(orphan)
        db.refresh(done)
        assert orphan.status == "error"
        assert orphan.finished_at is not None
        assert "superseded" in (orphan.error or "")
        # Other datasources untouched
        assert done.status == "success"
    finally:
        db.rollback()
        if store is not None:
            db.query(SyncRun).filter(SyncRun.store_id == store.id).delete(synchronize_session=False)
            db.query(DataSource).filter(DataSource.store_id == store.id).delete(synchronize_session=False)
            db.query(Store).filter(Store.id == store.id).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_mark_superseded_runs_noop_without_running_rows():
    from app.db.database import SessionLocal
    from app.sync.runs import mark_superseded_runs

    db = SessionLocal()
    try:
        assert mark_superseded_runs(db, None, "") == 0
        assert mark_superseded_runs(db, "no-store", "no-datasource") == 0
    finally:
        db.close()


# --- 2. POST /v1/stores production guard ---------------------------------


def test_create_store_refused_in_production(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    response = client.post("/v1/stores", json={"name": "Prod Store"})
    assert response.status_code == 403
    assert "signup" in response.json()["detail"].lower()


def test_create_store_still_works_outside_production(client):
    response = client.post("/v1/stores", json={"name": f"dev-{os.urandom(3).hex()}"})
    assert response.status_code in (200, 201)
    assert response.json().get("api_key")


# --- 3. ALLOW_LOCAL_DATASOURCE_HOSTS refused in production ----------------


def test_allow_local_datasource_hosts_refused_in_production():
    from pydantic import ValidationError

    from app.core.config import Settings

    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
    old_flag = os.environ.get("ALLOW_LOCAL_DATASOURCE_HOSTS")
    os.environ["ALLOW_LOCAL_DATASOURCE_HOSTS"] = "true"
    try:
        with pytest.raises(ValidationError) as excinfo:
            Settings(
                environment="production",
                database_url="postgresql://app:secret@db.example.com:5432/app",
                credential_encryption_key=key,
                jwt_secret_key="x" * 40,
                redis_url="redis://redis.example.com:6379/0",
                cors_allow_origins="https://example.com",
            )
        assert "ALLOW_LOCAL_DATASOURCE_HOSTS" in str(excinfo.value)
    finally:
        if old_flag is None:
            os.environ.pop("ALLOW_LOCAL_DATASOURCE_HOSTS", None)
        else:
            os.environ["ALLOW_LOCAL_DATASOURCE_HOSTS"] = old_flag


# --- 4. SSRF literal encodings -------------------------------------------


@pytest.fixture
def _strict_ssrf(monkeypatch):
    # conftest enables the dev-only local-host override suite-wide; pin it
    # off so these tests see production-default strict behaviour.
    monkeypatch.delenv("ALLOW_LOCAL_DATASOURCE_HOSTS", raising=False)


@pytest.mark.usefixtures("_strict_ssrf")
@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",
        "http://0x7f000001/",
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.0.1/",
    ],
)
def test_ssrf_literal_encodings_rejected(url):
    from app.knowledge.crawler import is_private_host

    assert is_private_host(url) is True


@pytest.mark.usefixtures("_strict_ssrf")
def test_ssrf_public_literal_allowed():
    from app.knowledge.crawler import is_private_host

    assert is_private_host("http://8.8.8.8/") is False
    assert is_private_host("https://example.com/products") is False


# --- 5. OpenGraph product extraction ---------------------------------------


OG_PRODUCT_HTML = """<!doctype html>
<html><head>
<title>Classic Watch</title>
<meta property="og:type" content="product" />
<meta property="og:title" content="Classic Watch W-100" />
<meta property="og:description" content="A stainless steel classic watch" />
<meta property="og:image" content="/images/watch.jpg" />
<meta property="og:url" content="https://shop.example.com/watch" />
<meta property="product:price:amount" content="249.00" />
<meta property="product:price:currency" content="USD" />
<meta property="product:sku" content="W-100" />
<meta property="product:brand" content="Acme" />
</head><body><h1>Classic Watch</h1><p>Stainless steel.</p></body></html>"""

OG_NON_PRODUCT_HTML = """<!doctype html>
<html><head>
<title>About us</title>
<meta property="og:type" content="website" />
<meta property="og:title" content="About us" />
</head><body><p>We sell watches.</p></body></html>"""


def test_og_product_extraction():
    from app.crawler.parser import extract_og_product, parse_page

    rows = extract_og_product(OG_PRODUCT_HTML, "https://shop.example.com/watch")
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Classic Watch W-100"
    assert row["sku"] == "W-100"
    assert row["brand"] == "Acme"
    assert row["offers"]["price"] == "249.00"
    assert row["offers"]["priceCurrency"] == "USD"
    assert row["image"] == "https://shop.example.com/images/watch.jpg"

    # Integrated into parse_page's structured_data (deduped against other
    # extractors) so web_ingestion picks it up without JSON-LD.
    parsed = parse_page(OG_PRODUCT_HTML, "https://shop.example.com/watch")
    products = [
        item for item in parsed["structured_data"]
        if str(item.get("@type", "")).casefold() == "product"
    ]
    assert any(item.get("name") == "Classic Watch W-100" for item in products)


def test_og_extraction_ignores_non_product_pages():
    from app.crawler.parser import extract_og_product

    assert extract_og_product(OG_NON_PRODUCT_HTML, "https://shop.example.com/about") == []


# --- 6. /v1/images dashboard detection matches /v1/chat -------------------


@pytest.mark.asyncio
async def test_images_dashboard_detection_uses_jwt_validation():
    """A request with an INVALID Bearer token must NOT be treated as a
    merchant dashboard request even when no x-api-key is present —
    matching /v1/chat's rule (header presence is not identity)."""
    from types import SimpleNamespace

    from app.auth.dashboard_auth import is_dashboard_request_for_store
    from app.db.database import SessionLocal
    from app.db.models import Store

    db = SessionLocal()
    store = None
    try:
        store = Store(name=f"imgauth-{os.urandom(3).hex()}", plan="starter")
        db.add(store)
        db.commit()
        request = SimpleNamespace(headers={"authorization": "Bearer not-a-real-jwt"})
        assert await is_dashboard_request_for_store(request, db, store) is False

        request_empty = SimpleNamespace(headers={})
        assert await is_dashboard_request_for_store(request_empty, db, store) is False
    finally:
        if store is not None:
            db.delete(store)
            db.commit()
        db.close()
