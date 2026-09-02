"""
Stripe integration.

Three entry points, each mapped to a route in app/api/routes/billing.py:

* `create_checkout_session` — merchant clicks "Upgrade to Growth" ->
  redirected to Stripe-hosted Checkout for a new subscription.
* `create_portal_session` — merchant clicks "Manage billing" ->
  redirected to Stripe's hosted Customer Portal (update card, view
  invoices, cancel).
* `handle_webhook_event` — Stripe calls back after checkout completes
  or a subscription changes/cancels/fails payment; this is the ONLY
  code path allowed to write `Store.plan` / `.monthly_budget` /
  `.stripe_subscription_status` for a paid plan, precisely because it
  reflects what Stripe actually charged rather than what a request
  claims happened. Signature-verified (see verify_webhook_signature)
  so an attacker can't POST a fake "upgrade me" event.
"""

from __future__ import annotations

import logging

import stripe
from sqlalchemy.orm import Session

from app.billing.plans import get_plan
from app.core.config import settings
from app.db.models import Store

logger = logging.getLogger(__name__)


class BillingNotConfigured(Exception):
    """Raised when STRIPE_SECRET_KEY isn't set — billing routes 503."""


class InvalidPlan(Exception):
    pass


def _client() -> stripe.StripeClient:
    if not settings.stripe_secret_key:
        raise BillingNotConfigured("STRIPE_SECRET_KEY is not configured")
    return stripe.StripeClient(settings.stripe_secret_key)


def _ensure_stripe_customer(db: Session, store: Store) -> str:
    if store.stripe_customer_id:
        return store.stripe_customer_id

    client = _client()
    customer = client.v1.customers.create(
        params={
            "name": store.name,
            "metadata": {"store_id": store.id},
        }
    )
    store.stripe_customer_id = customer.id
    db.add(store)
    db.commit()
    db.refresh(store)
    return customer.id


def create_checkout_session(db: Session, store: Store, plan_name: str) -> str:
    """Returns the Stripe-hosted Checkout URL to redirect the merchant to."""

    plan = get_plan(plan_name)
    if plan is None or plan.stripe_price_id is None:
        raise InvalidPlan(
            f"'{plan_name}' has no billable Stripe price configured"
        )

    client = _client()
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

    client = _client()
    session = client.v1.billing_portal.sessions.create(
        params={
            "customer": store.stripe_customer_id,
            "return_url": f"{settings.frontend_url}/billing",
        }
    )
    return session.url


def verify_webhook_signature(payload: bytes, sig_header: str) -> stripe.Event:
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured("STRIPE_WEBHOOK_SECRET is not configured")

    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )


def _plan_name_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan in (get_plan("starter"), get_plan("growth"), get_plan("pro")):
        if plan is not None and plan.stripe_price_id == price_id:
            return plan.name
    return None


def handle_webhook_event(db: Session, event: stripe.Event) -> None:
    """
    Applies a verified Stripe event to the matching Store. Unknown
    event types are ignored (Stripe sends many we don't act on);
    events for a store_id we can't resolve are logged and skipped
    rather than raising, so a Stripe retry storm can't take the
    endpoint down.
    """

    event_type = event["type"]
    obj = event["data"]["object"]

    store: Store | None = None

    store_id = (obj.get("metadata") or {}).get("store_id") or obj.get(
        "client_reference_id"
    )
    if store_id:
        store = db.query(Store).filter(Store.id == store_id).first()
    if store is None and obj.get("customer"):
        store = (
            db.query(Store)
            .filter(Store.stripe_customer_id == obj["customer"])
            .first()
        )

    if store is None:
        logger.warning(
            "stripe webhook %s: no matching store (customer=%s, store_id=%s)",
            event_type,
            obj.get("customer"),
            store_id,
        )
        return

    if event_type == "checkout.session.completed":
        subscription_id = obj.get("subscription")
        if subscription_id:
            store.stripe_subscription_id = subscription_id
        if obj.get("customer"):
            store.stripe_customer_id = obj["customer"]
        db.add(store)
        db.commit()

    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        store.stripe_subscription_id = obj["id"]
        store.stripe_subscription_status = obj["status"]

        price_id = None
        items = (obj.get("items") or {}).get("data") or []
        if items:
            price_id = items[0].get("price", {}).get("id")
        plan_name = _plan_name_from_price_id(price_id)

        if plan_name and obj["status"] in ("active", "trialing"):
            plan = get_plan(plan_name)
            store.plan = plan.name
            store.monthly_budget = plan.monthly_budget

        db.add(store)
        db.commit()

    elif event_type == "customer.subscription.deleted":
        store.stripe_subscription_status = "canceled"
        # Fall back to the free plan rather than leaving a stale
        # paid budget in place after the subscription actually ends.
        starter = get_plan("starter")
        store.plan = starter.name
        store.monthly_budget = starter.monthly_budget
        db.add(store)
        db.commit()

    elif event_type == "invoice.payment_failed":
        store.stripe_subscription_status = "past_due"
        db.add(store)
        db.commit()

    else:
        logger.info("stripe webhook %s: no handler, ignoring", event_type)
