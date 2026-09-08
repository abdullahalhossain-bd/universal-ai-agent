"""
Plan catalog.

Single source of truth for what a plan name means (monthly AI-spend
budget, in app.usage's currency unit) and, for paid plans, which
Stripe recurring Price ID it maps to. app/api/routes/stores.py
(direct store creation) and app/billing/service.py (Stripe checkout)
both read from here so the two paths can never disagree about what
"growth" costs or includes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_budget: float
    label: str
    # None for the free/default plan — nothing to check out in Stripe.
    stripe_price_id: str | None


def _catalog() -> dict[str, Plan]:
    return {
        "starter": Plan(
            name="starter",
            monthly_budget=1.00,
            label="Starter",
            stripe_price_id=None,
        ),
        "growth": Plan(
            name="growth",
            monthly_budget=5.00,
            label="Growth",
            stripe_price_id=settings.stripe_price_growth,
        ),
        "pro": Plan(
            name="pro",
            monthly_budget=10.00,
            label="Pro",
            stripe_price_id=settings.stripe_price_pro,
        ),
    }


def get_plan(name: str) -> Plan | None:
    return _catalog().get(name.lower().strip())


def all_plans() -> list[Plan]:
    return list(_catalog().values())


# Backward-compatible with app/api/routes/stores.py's pre-existing
# {name: budget} mapping.
PLAN_BUDGETS: dict[str, float] = {p.name: p.monthly_budget for p in all_plans()}
