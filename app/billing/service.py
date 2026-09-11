"""Stripe billing integration with durable webhook idempotency."""

from __future__ import annotations

import logging

import stripe
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.plans import all_plans, get_plan
from app.core.config import settings
from app.db.models import Store

logger = logging.getLogger(__name__)


class BillingNotConfigured(Exception):
    pass


class InvalidPlan(Exception):
    pass


def _client() -> stripe.StripeClient:
    if not settings.stripe_secret_key:
        raise BillingNotConfigured("STRIPE_SECRET_KEY is not configured")
    return stripe.StripeClient(settings.stripe_secret_key)


def _ensure_stripe_customer(db: Session, store: Store) -> str:
    if store.stripe_customer_id:
        return store.stripe_customer_id
    customer = _client().v1.customers.create(
        params={"name": store.name, "metadata": {"store_id": store.id}}
    )
    store.stripe_customer_id = customer.id
    db.add(store)
    db.commit()
    db.refresh(store)
    return customer.id


def create_checkout_session(db: Session, store: Store, plan_name: str) -> str:
    client = _client()
    plan = get_plan(db, plan_name)
    if plan is None or plan.stripe_price_id is None:
        raise InvalidPlan(f"'{plan_name}' has no billable Stripe price configured")
    customer_id = _ensure_stripe_customer(db, store)
    session = client.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": customer_id,
            "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
            "success_url": f"{settings.frontend_url}/billing?checkout=success",
            "cancel_url": f"{settings.frontend_url}/billing?checkout=cancelled",
            "client_reference_id": store.id,
            "metadata": {"store_id": store.id, "plan": plan.name},
            "subscription_data": {"metadata": {"store_id": store.id, "plan": plan.name}},
        }
    )
    return session.url


def create_portal_session(db: Session, store: Store) -> str:
    if not store.stripe_customer_id:
        raise InvalidPlan("This store has no Stripe customer yet")
    session = _client().v1.billing_portal.sessions.create(
        params={"customer": store.stripe_customer_id, "return_url": f"{settings.frontend_url}/billing"}
    )
    return session.url


def verify_webhook_signature(payload: bytes, sig_header: str) -> stripe.Event:
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


def _plan_name_from_price_id(db: Session, price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan in all_plans(db):
        if plan.stripe_price_id == price_id:
            return plan.name
    return None


def _claim_webhook_event(db: Session, event: stripe.Event) -> bool:
    """Claim a Stripe event exactly once; duplicate deliveries are harmless."""
    try:
        db.execute(
            text(
                "INSERT INTO billing_webhook_events "
                "(id, event_type, processed_at) VALUES (:id, :event_type, CURRENT_TIMESTAMP)"
            ),
            {"id": str(event["id"]), "event_type": str(event["type"])},
        )
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        logger.info("stripe webhook %s already processed", event["id"])
        return False


def handle_webhook_event(db: Session, event: stripe.Event) -> None:
    """Apply a verified Stripe event exactly once to its store."""
    if not _claim_webhook_event(db, event):
        return

    event_type = event["type"]
    obj = event["data"]["object"]
    store: Store | None = None
    store_id = (obj.get("metadata") or {}).get("store_id") or obj.get("client_reference_id")

    if store_id:
        store = db.query(Store).filter(Store.id == store_id).first()
    if store is None and obj.get("customer"):
        store = db.query(Store).filter(Store.stripe_customer_id == obj["customer"]).first()

    if store is None:
        logger.warning("stripe webhook %s: no matching store", event_type)
        db.commit()
        return

    if event_type == "checkout.session.completed":
        if obj.get("subscription"):
            store.stripe_subscription_id = obj["subscription"]
        if obj.get("customer"):
            store.stripe_customer_id = obj["customer"]

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        store.stripe_subscription_id = obj["id"]
        store.stripe_subscription_status = obj["status"]
        items = (obj.get("items") or {}).get("data") or []
        price_id = items[0].get("price", {}).get("id") if items else None
        plan_name = _plan_name_from_price_id(db, price_id)

        # Only active/trialing subscriptions grant the paid entitlement.
        # past_due/unpaid remain visible while Stripe retries payment.
        if plan_name and obj["status"] in ("active", "trialing"):
            plan = get_plan(db, plan_name)
            store.plan = plan.name
            store.monthly_budget = plan.monthly_budget

    elif event_type == "customer.subscription.deleted":
        store.stripe_subscription_status = "canceled"
        starter = get_plan(db, "starter")
        store.plan = starter.name
        store.monthly_budget = starter.monthly_budget
        store.stripe_subscription_id = None

    elif event_type == "invoice.payment_failed":
        # Stripe can retry invoices; do not immediately downgrade a merchant.
        store.stripe_subscription_status = "past_due"

    elif event_type == "invoice.paid":
        if store.stripe_subscription_status == "past_due":
            store.stripe_subscription_status = "active"

    else:
        logger.info("stripe webhook %s: no handler, ignoring", event_type)

    db.add(store)
    db.commit()
