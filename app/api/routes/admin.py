"""
Platform admin: the operator's (your) own login, entirely separate
from any merchant's dashboard `User` — see app.db.models.PlatformAdmin
and app.auth.admin_session for why the credential itself is kept
disjoint. Everything under this router can see and act across every
tenant, so every route here is gated on `get_current_admin`; nothing
here is reachable with a merchant's `x-api-key` or dashboard JWT.

There is deliberately no `/v1/admin/signup` — accounts are created
out-of-band with `scripts/create_platform_admin.py`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.admin_auth import get_current_admin
from app.auth.admin_session import create_admin_access_token
from app.auth.password import verify_password
from app.billing.plans import PLAN_BUDGETS, all_plans
from app.core.features import FEATURE_CATALOG, catalog_payload, normalized_features
from app.db.database import get_db
from app.db.models import APIKey, DataSource, PlatformAdmin, Store, User
from app.usage.models import UsageRecord

router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: dict


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    # Same generic-error / constant-time-ish shape as the merchant
    # login (app/api/routes/auth.py) so this endpoint can't be used
    # to enumerate whether an admin account exists.
    generic_error = HTTPException(status_code=401, detail="Invalid email or password")

    admin = (
        db.query(PlatformAdmin)
        .filter(PlatformAdmin.email == payload.email.lower().strip())
        .first()
    )
    if admin is None:
        verify_password(payload.password, "$2b$12$" + "0" * 53)
        raise generic_error

    if not verify_password(payload.password, admin.password_hash):
        raise generic_error

    admin.last_login_at = datetime.utcnow()
    db.add(admin)
    db.commit()

    token = create_admin_access_token(admin_id=admin.id)
    return AdminLoginResponse(
        access_token=token,
        admin={"id": admin.id, "email": admin.email},
    )


@router.get("/me")
def admin_me(admin: PlatformAdmin = Depends(get_current_admin)):
    return {"id": admin.id, "email": admin.email, "created_at": admin.created_at.isoformat()}


# ---------------------------------------------------------------------------
# Platform-wide stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def platform_stats(
    admin: PlatformAdmin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total_stores = db.query(func.count(Store.id)).scalar() or 0
    active_stores = (
        db.query(func.count(Store.id)).filter(Store.status == "active").scalar() or 0
    )
    suspended_stores = (
        db.query(func.count(Store.id)).filter(Store.status == "suspended").scalar() or 0
    )
    by_plan = dict(
        db.query(Store.plan, func.count(Store.id)).group_by(Store.plan).all()
    )

    # This-calendar-month spend across every tenant, in the same
    # currency unit UsageRecord.estimated_cost already uses.
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    month_spend = (
        db.query(func.coalesce(func.sum(UsageRecord.estimated_cost), 0))
        .filter(UsageRecord.created_at >= month_start)
        .filter(UsageRecord.status == "completed")
        .scalar()
        or 0
    )

    return {
        "total_stores": total_stores,
        "active_stores": active_stores,
        "suspended_stores": suspended_stores,
        "stores_by_plan": {p: int(by_plan.get(p, 0)) for p in PLAN_BUDGETS},
        "month_to_date_spend": float(month_spend),
        "plans": [
            {"name": p.name, "label": p.label, "monthly_budget": p.monthly_budget}
            for p in all_plans()
        ],
    }


@router.get("/features")
def list_feature_catalog(admin: PlatformAdmin = Depends(get_current_admin)):
    """
    The fixed set of togglable AI "packages" (app.core.features), so
    the admin UI never has to hardcode package 1/2/3/4's keys or
    labels — it renders whatever this returns.
    """
    return {"features": catalog_payload()}


# ---------------------------------------------------------------------------
# Stores (cross-tenant)
# ---------------------------------------------------------------------------


def _store_summary(db: Session, store: Store) -> dict:
    user_count = db.query(func.count(User.id)).filter(User.store_id == store.id).scalar() or 0
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    month_spend = (
        db.query(func.coalesce(func.sum(UsageRecord.estimated_cost), 0))
        .filter(UsageRecord.store_id == store.id)
        .filter(UsageRecord.created_at >= month_start)
        .filter(UsageRecord.status == "completed")
        .scalar()
        or 0
    )
    return {
        "id": store.id,
        "name": store.name,
        "website_url": store.website_url,
        "plan": store.plan,
        "monthly_budget": float(store.monthly_budget),
        "status": store.status,
        "stripe_subscription_status": store.stripe_subscription_status,
        "user_count": user_count,
        "month_to_date_spend": float(month_spend),
        "enabled_features": normalized_features(store),
        "created_at": store.created_at.isoformat(),
    }


@router.get("/stores")
def list_stores(
    q: str | None = Query(default=None, description="Search by store name or website"),
    status: str | None = Query(default=None),
    plan: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: PlatformAdmin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Store)

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Store.name.ilike(like), Store.website_url.ilike(like)))
    if status:
        query = query.filter(Store.status == status)
    if plan:
        query = query.filter(Store.plan == plan)

    total = query.with_entities(func.count(Store.id)).scalar() or 0
    stores = (
        query.order_by(Store.created_at.desc()).offset(offset).limit(limit).all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "stores": [_store_summary(db, s) for s in stores],
    }


@router.get("/stores/{store_id}")
def get_store_detail(
    store_id: str,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    users = db.query(User).filter(User.store_id == store_id).all()
    api_keys = db.query(APIKey).filter(APIKey.store_id == store_id).all()
    datasources = db.query(DataSource).filter(DataSource.store_id == store_id).all()
    recent_usage = (
        db.query(UsageRecord)
        .filter(UsageRecord.store_id == store_id)
        .order_by(UsageRecord.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        **_store_summary(db, store),
        "users": [
            {"id": u.id, "email": u.email, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
            for u in users
        ],
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "revoked": k.revoked_at is not None,
                "created_at": k.created_at.isoformat(),
            }
            for k in api_keys
        ],
        "datasources": [
            {
                "id": d.id,
                "name": d.name,
                "connector_type": d.connector_type,
                "active": d.active,
                "last_sync_status": d.last_sync_status,
                "last_sync_at": d.last_sync_at.isoformat() if d.last_sync_at else None,
            }
            for d in datasources
        ],
        "recent_usage": [
            {
                "id": r.id,
                "route": r.route,
                "model": r.model,
                "estimated_cost": r.estimated_cost,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent_usage
        ],
    }


class UpdateStoreRequest(BaseModel):
    status: str | None = None
    plan: str | None = None
    monthly_budget: float | None = None
    # Partial merge, not replace — {"image_search": false} turns off
    # only package 2 and leaves whatever else was set untouched, so
    # the admin UI can PATCH one toggle at a time without first
    # re-fetching and re-sending every other flag.
    enabled_features: dict[str, bool] | None = None


_VALID_STATUSES = {"setup", "active", "suspended"}
_VALID_FEATURE_KEYS = {f.key for f in FEATURE_CATALOG}


@router.patch("/stores/{store_id}")
def update_store(
    store_id: str,
    payload: UpdateStoreRequest,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Use one of: {', '.join(sorted(_VALID_STATUSES))}.",
            )
        store.status = payload.status

    if payload.plan is not None:
        plan_name = payload.plan.lower().strip()
        if plan_name not in PLAN_BUDGETS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan. Use one of: {', '.join(PLAN_BUDGETS)}.",
            )
        store.plan = plan_name
        # A plan change updates the budget to that plan's default
        # unless the caller also passed an explicit monthly_budget
        # below (checked second so it always wins).
        store.monthly_budget = PLAN_BUDGETS[plan_name]

    if payload.monthly_budget is not None:
        if payload.monthly_budget < 0:
            raise HTTPException(status_code=400, detail="monthly_budget must be >= 0")
        store.monthly_budget = payload.monthly_budget

    if payload.enabled_features is not None:
        unknown = set(payload.enabled_features) - _VALID_FEATURE_KEYS
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown feature key(s): {', '.join(sorted(unknown))}. "
                f"Valid keys: {', '.join(sorted(_VALID_FEATURE_KEYS))}.",
            )
        # Merge, don't replace — see UpdateStoreRequest.enabled_features.
        # New dict (not mutate-in-place) so SQLAlchemy's change
        # detection on a JSON column actually notices the write.
        merged = dict(store.enabled_features or {})
        merged.update(payload.enabled_features)
        store.enabled_features = merged

    db.add(store)
    db.commit()
    db.refresh(store)

    return _store_summary(db, store)


# ---------------------------------------------------------------------------
# Usage (cross-tenant)
# ---------------------------------------------------------------------------


@router.get("/usage")
def list_usage(
    store_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: PlatformAdmin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(UsageRecord)
    if store_id:
        query = query.filter(UsageRecord.store_id == store_id)

    total = query.with_entities(func.count(UsageRecord.id)).scalar() or 0
    records = (
        query.order_by(UsageRecord.created_at.desc()).offset(offset).limit(limit).all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "usage": [
            {
                "id": r.id,
                "store_id": r.store_id,
                "route": r.route,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "estimated_cost": r.estimated_cost,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ],
    }