"""Platform admin: operator-only cross-tenant controls."""

from __future__ import annotations
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session
from app.auth.admin_auth import get_current_admin
from app.auth.admin_session import create_admin_access_token
from app.auth.password import verify_password
from app.billing.plans import PLAN_BUDGETS, all_plans
from app.core.features import FEATURE_CATALOG, catalog_payload, normalized_features
from app.db.database import get_db, engine
from app.db.admin_audit import AdminAuditLog
from app.db.models import APIKey, DataSource, PlatformAdmin, Store, User
from app.usage.models import UsageRecord

router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])

class AdminLoginRequest(BaseModel):
    email: str
    password: str

class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: dict

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    generic_error = HTTPException(status_code=401, detail="Invalid email or password")
    admin = db.query(PlatformAdmin).filter(PlatformAdmin.email == payload.email.lower().strip()).first()
    if admin is None:
        verify_password(payload.password, "$2b$12$" + "0" * 53)
        raise generic_error
    if not verify_password(payload.password, admin.password_hash):
        raise generic_error
    admin.last_login_at = datetime.utcnow()
    db.add(admin); db.commit()
    token = create_admin_access_token(admin_id=admin.id)
    return AdminLoginResponse(access_token=token, admin={"id": admin.id, "email": admin.email})

@router.get("/me")
def admin_me(admin: PlatformAdmin = Depends(get_current_admin)):
    return {"id": admin.id, "email": admin.email, "created_at": admin.created_at.isoformat()}

@router.get("/stats")
def platform_stats(admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_stores = db.query(func.count(Store.id)).scalar() or 0
    active_stores = db.query(func.count(Store.id)).filter(Store.status == "active").scalar() or 0
    suspended_stores = db.query(func.count(Store.id)).filter(Store.status == "suspended").scalar() or 0
    by_plan = dict(db.query(Store.plan, func.count(Store.id)).group_by(Store.plan).all())
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_spend = db.query(func.coalesce(func.sum(UsageRecord.estimated_cost), 0)).filter(UsageRecord.created_at >= month_start).filter(UsageRecord.status == "completed").scalar() or 0
    return {"total_stores": total_stores, "active_stores": active_stores, "suspended_stores": suspended_stores, "stores_by_plan": {p: int(by_plan.get(p, 0)) for p in PLAN_BUDGETS}, "month_to_date_spend": float(month_spend), "plans": [{"name": p.name, "label": p.label, "monthly_budget": p.monthly_budget} for p in all_plans()]}

@router.get("/features")
def list_feature_catalog(admin: PlatformAdmin = Depends(get_current_admin)):
    return {"features": catalog_payload()}

def _store_summary(db: Session, store: Store) -> dict:
    user_count = db.query(func.count(User.id)).filter(User.store_id == store.id).scalar() or 0
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_spend = db.query(func.coalesce(func.sum(UsageRecord.estimated_cost), 0)).filter(UsageRecord.store_id == store.id).filter(UsageRecord.created_at >= month_start).filter(UsageRecord.status == "completed").scalar() or 0
    return {"id": store.id, "name": store.name, "website_url": store.website_url, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "status": store.status, "stripe_subscription_status": store.stripe_subscription_status, "user_count": user_count, "month_to_date_spend": float(month_spend), "enabled_features": normalized_features(store), "created_at": store.created_at.isoformat()}

@router.get("/stores")
def list_stores(q: str | None = Query(default=None), status: str | None = Query(default=None), plan: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(Store)
    if q:
        like = f"%{q.strip()}%"; query = query.filter(or_(Store.name.ilike(like), Store.website_url.ilike(like)))
    if status: query = query.filter(Store.status == status)
    if plan: query = query.filter(Store.plan == plan)
    total = query.with_entities(func.count(Store.id)).scalar() or 0
    stores = query.order_by(Store.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "stores": [_store_summary(db, s) for s in stores]}

@router.get("/stores/{store_id}")
def get_store_detail(store_id: str, admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None: raise HTTPException(status_code=404, detail="Store not found")
    users = db.query(User).filter(User.store_id == store_id).all()
    api_keys = db.query(APIKey).filter(APIKey.store_id == store_id).all()
    datasources = db.query(DataSource).filter(DataSource.store_id == store_id).all()
    recent_usage = db.query(UsageRecord).filter(UsageRecord.store_id == store_id).order_by(UsageRecord.created_at.desc()).limit(20).all()
    return {**_store_summary(db, store), "users": [{"id": u.id, "email": u.email, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None} for u in users], "api_keys": [{"id": k.id, "name": k.name, "key_prefix": k.key_prefix, "revoked": k.revoked_at is not None, "created_at": k.created_at.isoformat()} for k in api_keys], "datasources": [{"id": d.id, "name": d.name, "connector_type": d.connector_type, "active": d.active, "last_sync_status": d.last_sync_status, "last_sync_at": d.last_sync_at.isoformat() if d.last_sync_at else None} for d in datasources], "recent_usage": [{"id": r.id, "route": r.route, "model": r.model, "estimated_cost": r.estimated_cost, "status": r.status, "created_at": r.created_at.isoformat()} for r in recent_usage]}

class UpdateStoreRequest(BaseModel):
    status: str | None = None
    plan: str | None = None
    monthly_budget: float | None = None
    enabled_features: dict[str, bool] | None = None

_VALID_STATUSES = {"setup", "active", "suspended"}
_VALID_FEATURE_KEYS = {f.key for f in FEATURE_CATALOG}

@router.patch("/stores/{store_id}")
def update_store(store_id: str, payload: UpdateStoreRequest, admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None: raise HTTPException(status_code=404, detail="Store not found")
    before = {"status": store.status, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "enabled_features": normalized_features(store)}
    if payload.status is not None:
        if payload.status not in _VALID_STATUSES: raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {', '.join(sorted(_VALID_STATUSES))}.")
        store.status = payload.status
    if payload.plan is not None:
        plan_name = payload.plan.lower().strip()
        if plan_name not in PLAN_BUDGETS: raise HTTPException(status_code=400, detail=f"Invalid plan. Use one of: {', '.join(PLAN_BUDGETS)}.")
        store.plan = plan_name; store.monthly_budget = PLAN_BUDGETS[plan_name]
    if payload.monthly_budget is not None:
        if payload.monthly_budget < 0: raise HTTPException(status_code=400, detail="monthly_budget must be >= 0")
        store.monthly_budget = payload.monthly_budget
    if payload.enabled_features is not None:
        unknown = set(payload.enabled_features) - _VALID_FEATURE_KEYS
        if unknown: raise HTTPException(status_code=400, detail=f"Unknown feature key(s): {', '.join(sorted(unknown))}. Valid keys: {', '.join(sorted(_VALID_FEATURE_KEYS))}.")
        merged = dict(store.enabled_features or {}); merged.update(payload.enabled_features); store.enabled_features = merged
    db.add(store)
    after = {"status": store.status, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "enabled_features": normalized_features(store)}
    db.add(AdminAuditLog(admin_id=admin.id, action="store.update", store_id=store.id, details=json.dumps({"before": before, "after": after}, ensure_ascii=False)))
    db.commit(); db.refresh(store)
    return _store_summary(db, store)

@router.get("/usage")
def list_usage(store_id: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(UsageRecord)
    if store_id: query = query.filter(UsageRecord.store_id == store_id)
    total = query.with_entities(func.count(UsageRecord.id)).scalar() or 0
    records = query.order_by(UsageRecord.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "usage": [{"id": r.id, "store_id": r.store_id, "route": r.route, "model": r.model, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "estimated_cost": r.estimated_cost, "status": r.status, "created_at": r.created_at.isoformat()} for r in records]}

@router.get("/system-health")
async def system_health(admin: PlatformAdmin = Depends(get_current_admin)):
    checks = {"database": "ok", "redis": "unknown", "api": "ok"}
    try:
        await __import__("asyncio").to_thread(lambda: engine.connect().execute(text("SELECT 1")).close())
    except Exception: checks["database"] = "error"
    try:
        from app.core.redis import redis_client
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception: checks["redis"] = "error"
    return {"status": "ok" if all(v == "ok" for v in checks.values()) else "degraded", "checks": checks}
