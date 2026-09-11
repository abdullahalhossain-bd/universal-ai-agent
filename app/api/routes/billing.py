"""
Billing routes.

Merchant-scoped billing and usage endpoints. Subscription state is changed
only by verified Stripe webhooks; dashboard endpoints only read billing state
or create Stripe-hosted Checkout/Portal sessions.
"""

from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.billing import service
from app.billing.plans import all_plans
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Store
from app.usage.repository import UsageRepository
from app.usage.models import UsageRecord

router = APIRouter(prefix="/v1/billing", tags=["billing"])


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    return {
        "plans": [
            {
                "name": p.name,
                "label": p.label,
                "monthly_budget": p.monthly_budget,
                "billable": p.stripe_price_id is not None,
            }
            for p in all_plans(db)
        ]
    }


@router.get("/summary")
def billing_summary(
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    usage_repo = UsageRepository(db)
    spent = float(usage_repo.get_monthly_usage(store.id))
    budget = float(store.monthly_budget)
    usage_percent = (spent / budget * 100.0) if budget > 0 else 100.0
    return {
        "plan": store.plan,
        "monthly_budget": budget,
        "spent_this_month": spent,
        "remaining_budget": max(0.0, budget - spent),
        "usage_percent": min(100.0, max(0.0, usage_percent)),
        "subscription_status": store.stripe_subscription_status,
        "has_payment_method": store.stripe_customer_id is not None,
        "usage_warning": (
            "critical" if usage_percent >= 100 else
            "high" if usage_percent >= 80 else
            "medium" if usage_percent >= 60 else None
        ),
    }


@router.get("/usage")
def billing_usage(
    limit: int = 10,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 50))
    records = (
        db.query(UsageRecord)
        .filter(UsageRecord.store_id == store.id, UsageRecord.status == "completed")
        .order_by(UsageRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "usage": [
            {
                "id": r.id,
                "route": r.route,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "estimated_cost": r.estimated_cost,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    }


@router.get("/invoices")
def billing_invoices(
    limit: int = Query(10, ge=1, le=25),
    store: Store = Depends(get_current_store),
):
    """Return the merchant's recent Stripe invoices without exposing IDs for another store."""
    if not store.stripe_customer_id:
        return {"invoices": []}
    try:
        client = service._client()
        invoices = client.v1.invoices.list(
            params={"customer": store.stripe_customer_id, "limit": limit}
        )
        rows = []
        for invoice in invoices.data:
            rows.append({
                "id": invoice.id,
                "number": invoice.number,
                "status": invoice.status,
                "currency": invoice.currency,
                "amount_due": invoice.amount_due,
                "amount_paid": invoice.amount_paid,
                "total": invoice.total,
                "created": invoice.created,
                "period_start": invoice.period_start,
                "period_end": invoice.period_end,
                "hosted_invoice_url": invoice.hosted_invoice_url,
                "invoice_pdf": invoice.invoice_pdf,
            })
        return {"invoices": rows}
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail="Unable to load billing history right now") from exc


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
