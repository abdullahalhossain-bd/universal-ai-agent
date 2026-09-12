"""
Billing: plan catalog (no external calls), checkout/portal routes
when Stripe isn't configured (should fail loudly with 503, never
silently pretend to succeed), and the webhook handler's DB-side
effects given a fake-but-well-formed Stripe event object (no network
call to Stripe — app.billing.service.handle_webhook_event only reads
the event dict, it never calls the Stripe API itself).
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


@requires_postgres
def test_plan_catalog_has_starter_growth_pro(db_session):
    from app.billing.plans import all_plans

    names = {p.name for p in all_plans(db_session)}
    assert names == {"starter", "growth", "pro"}

    starter = next(p for p in all_plans(db_session) if p.name == "starter")
    assert starter.stripe_price_id is None  # free plan, nothing to bill


@requires_postgres
def test_list_plans_route_has_no_auth_requirement(client):
    resp = client.get("/v1/billing/plans")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["plans"]}
    assert names == {"starter", "growth", "pro"}


def test_checkout_session_without_stripe_configured_returns_503(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", None)

    # No auth at all -> 401 before ever reaching Stripe config.
    resp = client.post("/v1/billing/checkout-session", json={"plan": "growth"})
    assert resp.status_code == 401


@requires_postgres
def test_checkout_session_503_when_stripe_not_configured_for_authed_store(
    client, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", None)

    email = f"billing-{uuid.uuid4().hex[:8]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "store_name": "Billing Test Shop",
        },
    )
    token = signup.json()["access_token"]

    resp = client.post(
        "/v1/billing/checkout-session",
        json={"plan": "growth"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


@requires_postgres
def test_checkout_session_rejects_unbillable_plan(client, monkeypatch, db_session):
    from app.billing import plans as plans_module
    from app.core.config import settings
    from app.db.models import BillingPlan

    # Pretend Stripe IS configured, but growth has no price id -> the
    # service layer should still reject before calling Stripe.
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")

    growth = db_session.query(BillingPlan).filter(BillingPlan.name == "growth").first()
    original_price_id = growth.stripe_price_id
    growth.stripe_price_id = None
    db_session.add(growth)
    db_session.commit()
    plans_module.invalidate_cache()

    try:
        email = f"noprice-{uuid.uuid4().hex[:8]}@example.com"
        signup = client.post(
            "/v1/auth/signup",
            json={
                "email": email,
                "password": "correct horse battery staple",
                "store_name": "No Price Shop",
            },
        )
        token = signup.json()["access_token"]

        resp = client.post(
            "/v1/billing/checkout-session",
            json={"plan": "growth"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
    finally:
        growth.stripe_price_id = original_price_id
        db_session.add(growth)
        db_session.commit()
        plans_module.invalidate_cache()


# ---------------------------------------------------------------------------
# Webhook event application (no real Stripe call — event is a plain dict)
# ---------------------------------------------------------------------------


def _fake_event(event_type: str, obj: dict, *, event_id: str | None = None) -> dict:
    # Real Stripe events always carry a top-level `id` (the event's own
    # id, distinct from `data.object.id`) — `_claim_webhook_event` uses
    # it as the idempotency-ledger primary key. Default to a fresh
    # unique id per call so unrelated tests never collide on the
    # `billing_webhook_events` unique constraint.
    return {"id": event_id or f"evt_{uuid.uuid4().hex[:24]}", "type": event_type, "data": {"object": obj}}


@requires_postgres
def test_webhook_subscription_updated_applies_plan_and_budget(client, db_session, monkeypatch):
    from app.billing import plans as plans_module
    from app.billing import service
    from app.db.models import BillingPlan, Store

    growth = db_session.query(BillingPlan).filter(BillingPlan.name == "growth").first()
    original_price_id = growth.stripe_price_id
    growth.stripe_price_id = "price_growth_test"
    db_session.add(growth)
    db_session.commit()
    plans_module.invalidate_cache()

    try:
        store = Store(name="Webhook Shop", plan="starter", monthly_budget=1.0)
        db_session.add(store)
        db_session.commit()
        db_session.refresh(store)

        # Unique per run: stripe_subscription_id is unique across stores,
        # and the store row outlives this test in a persistent database.
        subscription_id = f"sub_{uuid.uuid4().hex[:12]}"

        event = _fake_event(
            "customer.subscription.updated",
            {
                "id": subscription_id,
                "status": "active",
                "customer": "cus_123",
                "metadata": {"store_id": store.id},
                "items": {"data": [{"price": {"id": "price_growth_test"}}]},
            },
        )

        service.handle_webhook_event(db_session, event)

        db_session.refresh(store)
        assert store.plan == "growth"
        assert float(store.monthly_budget) == 5.00
        assert store.stripe_subscription_status == "active"
        assert store.stripe_subscription_id == subscription_id
    finally:
        growth.stripe_price_id = original_price_id
        db_session.add(growth)
        db_session.commit()
        plans_module.invalidate_cache()


@requires_postgres
def test_webhook_subscription_deleted_falls_back_to_starter(client, db_session):
    from app.billing import service
    from app.db.models import Store

    store = Store(
        name="Cancelling Shop",
        plan="pro",
        monthly_budget=10.0,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)

    event = _fake_event(
        "customer.subscription.deleted",
        {"id": "sub_456", "customer": store.stripe_customer_id, "metadata": {}},
    )

    service.handle_webhook_event(db_session, event)

    db_session.refresh(store)
    assert store.plan == "starter"
    assert float(store.monthly_budget) == 1.00
    assert store.stripe_subscription_status == "canceled"


@requires_postgres
def test_webhook_for_unknown_store_does_not_raise(db_session):
    from app.billing import service

    event = _fake_event(
        "customer.subscription.updated",
        {
            "id": "sub_ghost",
            "status": "active",
            "customer": "cus_does_not_exist",
            "metadata": {},
            "items": {"data": []},
        },
    )
    # Must not raise — a webhook retry storm for a deleted store
    # shouldn't be able to 500 the endpoint.
    service.handle_webhook_event(db_session, event)


@requires_postgres
def test_webhook_payment_failed_marks_past_due(db_session):
    from app.billing import service
    from app.db.models import Store

    store = Store(
        name="Past Due Shop",
        plan="growth",
        monthly_budget=5.0,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)

    event = _fake_event(
        "invoice.payment_failed",
        {"customer": store.stripe_customer_id, "metadata": {}},
    )
    service.handle_webhook_event(db_session, event)

    db_session.refresh(store)
    assert store.stripe_subscription_status == "past_due"
    # Plan/budget untouched by a failed payment alone — Stripe will
    # send a subscription.updated (-> canceled/unpaid) separately if
    # it actually gives up on the subscription.
    assert store.plan == "growth"
