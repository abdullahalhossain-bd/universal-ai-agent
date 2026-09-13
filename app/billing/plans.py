"""
Plan catalog — DB-driven.

Plans (starter/growth/pro, budgets, Stripe price IDs) live in the
`billing_plans` table (see app/db/models.py:BillingPlan) and are
managed by operators via /v1/admin/plans (app/api/routes/admin.py).
This used to be a hardcoded dict; moving it to the DB means adding,
retiring, or repricing a plan no longer needs a deploy.

app/api/routes/stores.py (direct store creation), app/api/routes/auth.py
(signup) and app/billing/service.py (Stripe checkout/webhooks) all read
from here so those paths can never disagree about what "growth" costs
or includes.

Reads are cached in-process (single-flight per worker, no TTL) because
this is on the hot path (every signup, every checkout attempt) and the
catalog changes rarely. Any admin write MUST call invalidate_cache()
in the same request so the next read picks it up — see
app/api/routes/admin.py's plan routes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import BillingPlan


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_budget: float
    label: str
    # None means "not billable via Stripe" (the free/default plan, or
    # a paid plan whose price ID hasn't been configured yet).
    stripe_price_id: str | None


_cache_lock = threading.Lock()
_cache: dict[str, Plan] | None = None


def _load_from_db(db: Session) -> dict[str, Plan]:
    rows = (
        db.query(BillingPlan)
        .filter(BillingPlan.is_active.is_(True))
        .order_by(BillingPlan.sort_order, BillingPlan.name)
        .all()
    )
    return {
        row.name: Plan(
            name=row.name,
            monthly_budget=float(row.monthly_budget),
            label=row.label,
            stripe_price_id=row.stripe_price_id,
        )
        for row in rows
    }


def invalidate_cache() -> None:
    """
    Drop the cached catalog so the next read reloads from the DB.

    Call this after any write to `billing_plans` (create/update/
    deactivate) in the same request/transaction that made the change,
    and from tests that mutate BillingPlan rows directly.
    """

    global _cache
    with _cache_lock:
        _cache = None


def _catalog(db: Session) -> dict[str, Plan]:
    global _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
    fresh = _load_from_db(db)
    with _cache_lock:
        _cache = fresh
        return _cache


def get_plan(db: Session, name: str) -> Plan | None:
    return _catalog(db).get(name.lower().strip())


def all_plans(db: Session) -> list[Plan]:
    return list(_catalog(db).values())


def plan_budgets(db: Session) -> dict[str, float]:
    """Backward-compatible {name: monthly_budget} mapping."""

    return {p.name: p.monthly_budget for p in all_plans(db)}
