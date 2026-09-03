from __future__ import annotations
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.auth.admin_auth import get_current_admin
from app.db.database import get_db
from app.db.admin_audit import AdminAuditLog
from app.db.models import PlatformAdmin, Store
from app.chat.models import ChatSession, ChatMessage
from app.usage.models import UsageRecord

router = APIRouter(prefix="/v1/admin", tags=["platform-admin"])

@router.get("/analytics/overview")
def analytics_overview(days: int = Query(default=30, ge=1, le=365), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    usage = db.query(
        func.count(UsageRecord.id),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    ).filter(UsageRecord.created_at >= since, UsageRecord.status == "completed").one()
    conversations = db.query(func.count(ChatSession.id)).filter(ChatSession.created_at >= since).scalar() or 0
    messages = db.query(func.count(ChatMessage.id)).join(ChatSession, ChatMessage.session_id == ChatSession.id).filter(ChatMessage.created_at >= since).scalar() or 0
    return {"days": days, "usage_requests": int(usage[0] or 0), "input_tokens": int(usage[1] or 0), "output_tokens": int(usage[2] or 0), "ai_cost": float(usage[3] or 0), "conversations": int(conversations), "messages": int(messages)}

@router.get("/analytics/daily")
def analytics_daily(days: int = Query(default=30, ge=1, le=365), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(
        func.date(UsageRecord.created_at).label("day"),
        func.count(UsageRecord.id).label("requests"),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0).label("cost"),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0).label("output_tokens"),
    ).filter(UsageRecord.created_at >= since, UsageRecord.status == "completed").group_by(func.date(UsageRecord.created_at)).order_by(func.date(UsageRecord.created_at)).all()
    return {"days": days, "series": [{"date": str(r.day), "requests": int(r.requests), "cost": float(r.cost or 0), "input_tokens": int(r.input_tokens or 0), "output_tokens": int(r.output_tokens or 0)} for r in rows]}

@router.get("/conversations")
def admin_conversations(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), store_id: str | None = Query(default=None), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(ChatSession, Store).join(Store, Store.id == ChatSession.store_id)
    if store_id: q = q.filter(ChatSession.store_id == store_id)
    total = q.with_entities(func.count(ChatSession.id)).scalar() or 0
    rows = q.order_by(ChatSession.updated_at.desc()).offset(offset).limit(limit).all()
    result = []
    for session, store in rows:
        last = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.desc()).first()
        result.append({"conversation_id": session.conversation_key, "store_id": store.id, "store_name": store.name, "visitor_id": session.visitor_id, "updated_at": session.updated_at.isoformat(), "last_message": {"role": last.role, "content": last.content, "created_at": last.created_at.isoformat()} if last else None})
    return {"total": total, "limit": limit, "offset": offset, "conversations": result}

@router.get("/conversations/{conversation_id}")
def admin_conversation_detail(conversation_id: str, store_id: str = Query(...), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.store_id == store_id, ChatSession.conversation_key == conversation_id).first()
    if not session: return {"conversation_id": conversation_id, "store_id": store_id, "messages": []}
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc()).all()
    return {"conversation_id": conversation_id, "store_id": store_id, "visitor_id": session.visitor_id, "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat(), "messages": [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages]}

@router.get("/audit-logs")
def audit_logs(limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), store_id: str | None = Query(default=None), admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(AdminAuditLog)
    if store_id: q = q.filter(AdminAuditLog.store_id == store_id)
    total = q.with_entities(func.count(AdminAuditLog.id)).scalar() or 0
    rows = q.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "logs": [{"id": x.id, "admin_id": x.admin_id, "action": x.action, "store_id": x.store_id, "details": x.details, "created_at": x.created_at.isoformat()} for x in rows]}

@router.post("/audit-logs")
def create_audit_log(action: str, store_id: str | None = None, details: dict | None = None, admin: PlatformAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    row = AdminAuditLog(admin_id=admin.id, action=action[:100], store_id=store_id, details=json.dumps(details or {}, ensure_ascii=False))
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "created_at": row.created_at.isoformat()}
