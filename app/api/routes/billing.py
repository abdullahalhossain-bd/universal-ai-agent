"""
Billing routes.

`/checkout-session` and `/portal-session` are store-scoped (dashboard
session or x-api-key, via get_current_store) and only ever *redirect*
the merchant to Stripe — they never themselves change `Store.plan`.
`/webhook` is the only place a subscription change is applied to the
DB, and it trusts nothing but a validly-signed Stripe event.
"""

from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.billing import service
from app.billing.plans import all_plans
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Store
from app.usage.repository import UsageRepository

router = APIRouter(prefix="/v1/billing", tags=["billing"])


@router.get("/plans")
def list_plans():
    return {
        "plans": [
            {
                "name": p.name,
                "label": p.label,
                "monthly_budget": p.monthly_budget,
                "billable": p.stripe_price_id is not None,
            }
            for p in all_plans()
        ]
    }


@router.get("/summary")
def billing_summary(
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    usage_repo = UsageRepository(db)
    spent_this_month = usage_repo.get_monthly_usage(store.id)

    return {
        "plan": store.plan,
        "monthly_budget": float(store.monthly_budget),
        "spent_this_month": float(spent_this_month),
        "subscription_status": store.stripe_subscription_status,
        "has_payment_method": store.stripe_customer_id is not None,
    }


class CheckoutRequest(BaseModel):
    plan: str


@router.post("/checkout-session")
def create_checkout_session(
    payload: CheckoutRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    try:
        url = service.create_checkout_session(db, store, payload.plan)
    except service.BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.InvalidPlan as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"checkout_url": url}


@router.post("/portal-session")
def create_portal_session(
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    try:
        url = service.create_portal_session(db, store)
    except service.BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.InvalidPlan as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"portal_url": url}


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = service.verify_webhook_signature(payload, sig_header)
    except service.BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc

    service.handle_webhook_event(db, event)
    return {"received": True}
