"""
Admin plan-catalog management: /v1/admin/plans (list/create/update/
deactivate). These are the DB-driven replacement for what used to be
a hardcoded dict in app/billing/plans.py — see that module's docstring
and alembic/versions/0031_billing_plans.py for the full story.
"""

from __future__ import annotations

import uuid

import pytest

from tests.markers import requires_postgres, skip_unless_postgres


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


@pytest.fixture()
def admin_auth_headers(db_session):
    """Creates a real PlatformAdmin row and returns Authorization headers for it."""
    from app.auth.admin_session import create_admin_access_token
    from app.auth.password import hash_password
    from app.db.models import PlatformAdmin

    admin = PlatformAdmin(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("correct horse battery staple"),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    token = create_admin_access_token(admin_id=admin.id, session_version=admin.session_version)
    return {"Authorization": f"Bearer {token}"}


@requires_postgres
def test_list_plans_requires_admin_auth(client):
    resp = client.get("/v1/admin/plans")
    assert resp.status_code == 401


@requires_postgres
def test_list_plans_includes_seeded_catalog(client, admin_auth_headers):
    resp = client.get("/v1/admin/plans", headers=admin_auth_headers)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["plans"]}
    assert {"starter", "growth", "pro"} <= names


@requires_postgres
def test_create_update_and_deactivate_plan_round_trip(client, admin_auth_headers, db_session):
    from app.billing import plans as plans_module
    from app.db.models import BillingPlan

    name = f"custom_{uuid.uuid4().hex[:8]}"

    try:
        create_resp = client.post(
            "/v1/admin/plans",
            json={"name": name, "label": "Custom Plan", "monthly_budget": 2.5},
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert body["name"] == name
        assert body["monthly_budget"] == 2.5
        assert body["is_active"] is True

        # New plan is immediately visible on the merchant-facing route
        # (cache was invalidated by the create).
        plans_resp = client.get("/v1/billing/plans")
        assert name in {p["name"] for p in plans_resp.json()["plans"]}

        # Duplicate name is rejected.
        dup_resp = client.post(
            "/v1/admin/plans",
            json={"name": name, "label": "Dup", "monthly_budget": 1},
            headers=admin_auth_headers,
        )
        assert dup_resp.status_code == 409

        # Update budget.
        update_resp = client.patch(
            f"/v1/admin/plans/{name}",
            json={"monthly_budget": 7.5},
            headers=admin_auth_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["monthly_budget"] == 7.5

        # Deactivate: disappears from the merchant-facing route.
        delete_resp = client.delete(f"/v1/admin/plans/{name}", headers=admin_auth_headers)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["stores_still_on_plan"] == 0

        plans_resp = client.get("/v1/billing/plans")
        assert name not in {p["name"] for p in plans_resp.json()["plans"]}

        # But still visible (as inactive) on the full admin listing.
        admin_list = client.get("/v1/admin/plans", headers=admin_auth_headers)
        row = next(p for p in admin_list.json()["plans"] if p["name"] == name)
        assert row["is_active"] is False
    finally:
        db_session.query(BillingPlan).filter(BillingPlan.name == name).delete()
        db_session.commit()
        plans_module.invalidate_cache()


@requires_postgres
def test_create_plan_rejects_negative_budget(client, admin_auth_headers):
    resp = client.post(
        "/v1/admin/plans",
        json={"name": f"bad_{uuid.uuid4().hex[:8]}", "label": "Bad", "monthly_budget": -1},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 400


@requires_postgres
def test_update_unknown_plan_returns_404(client, admin_auth_headers):
    resp = client.patch(
        "/v1/admin/plans/does-not-exist",
        json={"monthly_budget": 5},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 404
