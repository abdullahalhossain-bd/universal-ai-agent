"""
API key authentication guards.

Two independent FastAPI dependencies implement API-key auth in this
codebase — `app.auth.api_key.get_api_key` (used by
`app.core.tenant.get_current_store` / `get_tenant_context`, which
most routers depend on) and `app.auth.dependency.authenticate_api_key`
(used directly by the image/knowledge routers). Both must enforce the
same rules: a key is required, must have the issued `pk_` prefix, and
must resolve to a non-revoked `APIKey` row. This file exercises both.

The no-DB-touch cases (missing header, wrong prefix) run everywhere.
The DB-backed cases (valid key resolves to the right store, revoked
key rejected, well-formed-but-unknown key rejected) need a real
Postgres connection — this project's `db_session`/`APIKey` model uses
a Postgres-only server, so those are gated behind `requires_postgres`
like the rest of the suite (see tests/test_budget_security.py,
tests/test_datasources.py).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from tests.markers import requires_postgres, skip_unless_postgres


# ---------------------------------------------------------------------------
# No-DB cases (run everywhere; get_api_key / authenticate_api_key both
# reject these before ever touching the database)
# ---------------------------------------------------------------------------


def test_get_api_key_rejects_missing_key():
    from app.auth.api_key import get_api_key

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(get_api_key(x_api_key=None, db=None))
    assert exc_info.value.status_code == 401


def test_get_api_key_rejects_wrong_prefix():
    from app.auth.api_key import get_api_key

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(get_api_key(x_api_key="sk_not_a_public_key", db=None))
    assert exc_info.value.status_code == 401


def test_authenticate_api_key_rejects_missing_key():
    from app.auth.dependency import authenticate_api_key

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(authenticate_api_key(x_api_key=None, db=None))
    assert exc_info.value.status_code == 401


def test_authenticate_api_key_rejects_wrong_prefix():
    from app.auth.dependency import authenticate_api_key

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(authenticate_api_key(x_api_key="not-even-close", db=None))
    assert exc_info.value.status_code == 401


def test_protected_routes_401_without_a_key(client):
    """
    End-to-end (no real DB needed — auth fails before any query):
    every store-scoped route must require x-api-key.
    """
    for method, path, body in [
        ("GET", "/v1/stores/me", None),
        ("GET", "/v1/products/search?q=shoe", None),
        ("GET", "/v1/datasources", None),
        ("POST", "/v1/images", None),
    ]:
        resp = client.request(method, path, json=body)
        assert resp.status_code in (401, 422), (
            f"{method} {path} should require auth, got {resp.status_code}"
        )
        if resp.status_code == 401:
            assert "key" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DB-backed cases
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    skip_unless_postgres()
    from app.db.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _create_store_and_key(db_session):
    from app.core.security import generate_api_key
    from app.db.models import APIKey, Store

    store = Store(
        name=f"auth-test-{uuid.uuid4()}",
        plan="starter",
        monthly_budget=1.0,
        status="active",
    )
    db_session.add(store)
    db_session.flush()

    raw_key, prefix, key_hash = generate_api_key()
    api_key = APIKey(store_id=store.id, key_prefix=prefix, key_hash=key_hash)
    db_session.add(api_key)
    db_session.commit()

    return store, api_key, raw_key


@requires_postgres
def test_valid_key_resolves_to_its_own_store(db_session):
    import asyncio

    from app.auth.api_key import get_api_key

    store, api_key, raw_key = _create_store_and_key(db_session)

    resolved = asyncio.run(get_api_key(x_api_key=raw_key, db=db_session))

    assert resolved.id == api_key.id
    assert resolved.store_id == store.id


@requires_postgres
def test_revoked_key_is_rejected(db_session):
    import asyncio
    from datetime import datetime

    from app.auth.api_key import get_api_key

    store, api_key, raw_key = _create_store_and_key(db_session)

    api_key.revoked_at = datetime.utcnow()
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_api_key(x_api_key=raw_key, db=db_session))
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


@requires_postgres
def test_well_formed_but_unknown_key_is_rejected(db_session):
    import asyncio

    from app.auth.api_key import get_api_key

    # Never issued — random but correctly prefixed/shaped.
    fake_key = f"pk_live_{uuid.uuid4().hex}{uuid.uuid4().hex}"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_api_key(x_api_key=fake_key, db=db_session))
    assert exc_info.value.status_code == 401


@requires_postgres
def test_one_stores_key_cannot_authenticate_as_another_store(db_session):
    """
    Not just "auth succeeds/fails" — the resolved store_id must be
    exactly the key's own store, never influenced by anything else
    in the request. This is the property every downstream tenant
    filter (Product, DataSource, ChatSession, ...) relies on.
    """
    import asyncio

    from app.auth.api_key import get_api_key

    store_a, _, raw_key_a = _create_store_and_key(db_session)
    store_b, _, raw_key_b = _create_store_and_key(db_session)

    resolved_a = asyncio.run(get_api_key(x_api_key=raw_key_a, db=db_session))
    resolved_b = asyncio.run(get_api_key(x_api_key=raw_key_b, db=db_session))

    assert resolved_a.store_id == store_a.id
    assert resolved_b.store_id == store_b.id
    assert resolved_a.store_id != resolved_b.store_id
