"""Merchant-only Customer and Inbox management APIs.

This router intentionally lives apart from the public/customer message routes:
public visitors never receive customer-management capabilities.
"""

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.auth.inbox_auth import get_current_inbox_user_and_store, require_inbox_csrf
from app.chat.models import ChatMessage, ChatSession
from app.db.customer import Customer, CustomerAuditLog, CustomerIdentity, CustomerIdentityHistory
from app.db.database import get_db
from app.db.models import Store, User
from app.db.visitor import VisitorProfile

router = APIRouter(prefix="/v1/customer-management", tags=["customer-management"])


class IdentityLinkRequest(BaseModel):
    identity_type: str = Field(pattern="^(email|phone)$")
    identity_value: str = Field(min_length=3, max_length=320)


class CustomerStatusRequest(BaseModel):
    status: str = Field(pattern="^(open|resolved|archived)$")


class CustomerMergeRequest(BaseModel):
    source_customer_id: str = Field(min_length=36, max_length=36)
    target_customer_id: str = Field(min_length=36, max_length=36)


def _encode_cursor(value: tuple[datetime, str] | None) -> str | None:
    if not value:
        return None
    raw = json.dumps({"ts": value[0].isoformat(), "id": value[1]}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(data["ts"]), str(data["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc


def _customer(db: Session, store_id: str, customer_id: str, lock: bool = False):
    query = db.query(Customer).filter(Customer.store_id == store_id, Customer.id == customer_id)
    if lock:
        query = query.with_for_update()
    return query.first()


def _audit(db: Session, store_id: str, customer_id: str | None, action: str, user: User, metadata=None, conversation_id=None):
    db.add(CustomerAuditLog(
        store_id=store_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        action=action,
        actor_type="merchant",
        actor_id=user.id,
        metadata_json=metadata or {},
        created_at=datetime.utcnow(),
    ))


def _customer_row(c: Customer):
    return {
        "customer_id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "first_seen_at": c.first_seen_at,
        "last_seen_at": c.last_seen_at,
        "anonymized_at": c.anonymized_at,
        "merged_into_customer_id": c.merged_into_customer_id,
    }


def _unread(db: Session, session: ChatSession) -> bool:
    if session.read_at is None:
        return db.query(ChatMessage.id).filter(ChatMessage.session_id == session.id, ChatMessage.role == "user").first() is not None
    return db.query(ChatMessage.id).filter(ChatMessage.session_id == session.id, ChatMessage.role == "user", ChatMessage.created_at > session.read_at).first() is not None


def _conversation_row(db: Session, s: ChatSession):
    last = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).order_by(ChatMessage.created_at.desc()).first()
    return {
        "conversation_id": s.conversation_key,
        "session_id": s.id,
        "customer_id": s.customer_id,
        "visitor_id": s.visitor_id,
        "mode": s.mode or "ai",
        "mode_owner": s.mode_owner or "ai",
        "status": s.status or "open",
        "unread": _unread(db, s),
        "read_at": s.read_at,
        "archived_at": s.archived_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "last_message": {"id": last.id, "role": last.role, "content": last.content, "created_at": last.created_at} if last else None,
    }


@router.get("/customers")
def list_customers(
    search: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    db: Session = Depends(get_db),
):
    _user, store = auth
    query = db.query(Customer).filter(Customer.store_id == store.id, Customer.merged_into_customer_id.is_(None))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(or_(func.lower(Customer.name).like(term), func.lower(Customer.email).like(term), func.lower(Customer.phone).like(term), Customer.id.like(f"%{search.strip()}%")))
    decoded = _decode_cursor(cursor)
    if decoded:
        ts, cid = decoded
        query = query.filter(or_(Customer.last_seen_at < ts, and_(Customer.last_seen_at == ts, Customer.id < cid)))
    rows = query.order_by(Customer.last_seen_at.desc(), Customer.id.desc()).limit(limit + 1).all()
    next_cursor = _encode_cursor((rows[limit - 1].last_seen_at, rows[limit - 1].id)) if len(rows) > limit else None
    return {"items": [_customer_row(c) for c in rows[:limit]], "next_cursor": next_cursor}


@router.get("/customers/{customer_id}")
def get_customer_profile(
    customer_id: str,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    db: Session = Depends(get_db),
):
    _user, store = auth
    customer = _customer(db, store.id, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.merged_into_customer_id:
        return {"merged": True, "redirect_customer_id": customer.merged_into_customer_id}
    identities = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == customer.id).order_by(CustomerIdentity.created_at.asc()).all()
    history = db.query(CustomerIdentityHistory).filter(CustomerIdentityHistory.store_id == store.id, CustomerIdentityHistory.customer_id == customer.id).order_by(CustomerIdentityHistory.created_at.desc()).limit(200).all()
    audit = db.query(CustomerAuditLog).filter(CustomerAuditLog.store_id == store.id, CustomerAuditLog.customer_id == customer.id).order_by(CustomerAuditLog.created_at.desc()).limit(200).all()
    conversations = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.customer_id == customer.id).order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()).limit(100).all()
    return {
        "customer": _customer_row(customer),
        "identities": [{"id": i.id, "type": i.identity_type, "value": i.identity_value, "created_at": i.created_at, "updated_at": i.updated_at} for i in identities],
        "conversations": [_conversation_row(db, s) for s in conversations],
        "identity_history": [{"id": h.id, "action": h.action, "identity_type": h.identity_type, "identity_value": h.identity_value, "from_customer_id": h.from_customer_id, "to_customer_id": h.to_customer_id, "actor_type": h.actor_type, "actor_id": h.actor_id, "metadata": h.metadata_json, "created_at": h.created_at} for h in history],
        "audit_log": [{"id": a.id, "action": a.action, "actor_type": a.actor_type, "actor_id": a.actor_id, "metadata": a.metadata_json, "conversation_id": a.conversation_id, "created_at": a.created_at} for a in audit],
    }


@router.post("/customers/{customer_id}/identities/link")
def link_identity(
    customer_id: str,
    payload: IdentityLinkRequest,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    customer = _customer(db, store.id, customer_id, lock=True)
    if customer is None or customer.merged_into_customer_id or customer.anonymized_at:
        raise HTTPException(status_code=404, detail="Active customer not found")
    value = payload.identity_value.strip().lower() if payload.identity_type == "email" else payload.identity_value.strip()
    existing = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.identity_type == payload.identity_type, CustomerIdentity.identity_value == value).with_for_update().first()
    if existing and existing.customer_id != customer.id:
        raise HTTPException(status_code=409, detail="Identity is already linked to another customer. Use the controlled merge flow.")
    if existing:
        return {"linked": True, "identity_id": existing.id, "already_linked": True}
    identity = CustomerIdentity(store_id=store.id, customer_id=customer.id, identity_type=payload.identity_type, identity_value=value)
    db.add(identity)
    db.add(CustomerIdentityHistory(store_id=store.id, customer_id=customer.id, action="linked_manual", identity_type=payload.identity_type, identity_value=value, to_customer_id=customer.id, actor_type="merchant", actor_id=user.id, created_at=datetime.utcnow()))
    if payload.identity_type == "email": customer.email = value
    else: customer.phone = value
    customer.updated_at = datetime.utcnow()
    _audit(db, store.id, customer.id, "identity_linked", user, {"identity_type": payload.identity_type})
    db.commit(); db.refresh(identity)
    return {"linked": True, "identity_id": identity.id}


@router.delete("/customers/{customer_id}/identities/{identity_id}")
def unlink_identity(
    customer_id: str,
    identity_id: str,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    customer = _customer(db, store.id, customer_id, lock=True)
    identity = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.id == identity_id, CustomerIdentity.customer_id == customer_id).with_for_update().first()
    if customer is None or identity is None:
        raise HTTPException(status_code=404, detail="Identity not found")
    count = db.query(CustomerIdentity.id).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == customer_id).count()
    if count <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the customer's only identity. An explicit customer anonymization or merge is required.")
    db.add(CustomerIdentityHistory(store_id=store.id, customer_id=customer.id, action="unlinked", identity_type=identity.identity_type, identity_value=identity.identity_value, from_customer_id=customer.id, actor_type="merchant", actor_id=user.id, created_at=datetime.utcnow()))
    _audit(db, store.id, customer.id, "identity_unlinked", user, {"identity_type": identity.identity_type})
    if identity.identity_type == "email" and customer.email == identity.identity_value: customer.email = None
    if identity.identity_type == "phone" and customer.phone == identity.identity_value: customer.phone = None
    db.delete(identity)
    customer.updated_at = datetime.utcnow()
    db.commit()
    return {"unlinked": True}


@router.post("/customers/merge")
def merge_customers(
    payload: CustomerMergeRequest,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    if payload.source_customer_id == payload.target_customer_id:
        raise HTTPException(status_code=400, detail="Source and target customer must be different")
    try:
        source = _customer(db, store.id, payload.source_customer_id, lock=True)
        target = _customer(db, store.id, payload.target_customer_id, lock=True)
        if source is None or target is None:
            raise HTTPException(status_code=404, detail="Source or target customer not found")
        if source.merged_into_customer_id or target.merged_into_customer_id or source.anonymized_at:
            raise HTTPException(status_code=409, detail="Source or target customer is not mergeable")
        now = datetime.utcnow()
        _audit(db, store.id, target.id, "merge_started", user, {"source_customer_id": source.id, "target_customer_id": target.id})
        for identity in db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == source.id).with_for_update().all():
            duplicate = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == target.id, CustomerIdentity.identity_type == identity.identity_type, CustomerIdentity.identity_value == identity.identity_value).with_for_update().first()
            identity_value, identity_type = identity.identity_value, identity.identity_type
            if duplicate:
                db.delete(identity); action = "identity_deduplicated"
            else:
                identity.customer_id = target.id; identity.updated_at = now; action = "identity_moved"
            db.add(CustomerIdentityHistory(store_id=store.id, customer_id=target.id, action=action, identity_type=identity_type, identity_value=identity_value, from_customer_id=source.id, to_customer_id=target.id, actor_type="merchant", actor_id=user.id, created_at=now))
        db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.customer_id == source.id).update({"customer_id": target.id}, synchronize_session=False)
        for field in ("name", "email", "phone"):
            if not getattr(target, field) and getattr(source, field):
                setattr(target, field, getattr(source, field))
        target.first_seen_at = min(target.first_seen_at, source.first_seen_at)
        target.last_seen_at = max(target.last_seen_at, source.last_seen_at)
        target.updated_at = now
        source.merged_into_customer_id = target.id
        source.updated_at = now
        db.add(CustomerIdentityHistory(store_id=store.id, customer_id=target.id, action="merged", from_customer_id=source.id, to_customer_id=target.id, actor_type="merchant", actor_id=user.id, metadata_json={"source_customer_id": source.id, "target_customer_id": target.id}, created_at=now))
        _audit(db, store.id, target.id, "merged", user, {"source_customer_id": source.id, "target_customer_id": target.id})
        db.commit(); db.refresh(target)
        return {"merged": True, "customer": _customer_row(target), "source_customer_id": source.id, "target_customer_id": target.id}
    except Exception:
        db.rollback()
        raise


@router.post("/customers/{customer_id}/anonymize")
def anonymize_customer(
    customer_id: str,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    try:
        customer = _customer(db, store.id, customer_id, lock=True)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        if customer.anonymized_at:
            return {"anonymized": True, "customer_id": customer.id}
        now = datetime.utcnow()
        for identity in db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == customer.id).with_for_update().all():
            db.add(CustomerIdentityHistory(store_id=store.id, customer_id=customer.id, action="anonymized", identity_type=identity.identity_type, identity_value="[redacted]", from_customer_id=customer.id, actor_type="merchant", actor_id=user.id, created_at=now))
            db.delete(identity)
        sessions = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.customer_id == customer.id).all()
        visitor_ids = {s.visitor_id for s in sessions if s.visitor_id and s.visitor_id != "anonymous"}
        if visitor_ids:
            db.query(VisitorProfile).filter(VisitorProfile.store_id == store.id, VisitorProfile.visitor_id.in_(visitor_ids)).update({"name": None, "email": None, "phone": None}, synchronize_session=False)
        customer.name = None; customer.email = None; customer.phone = None; customer.anonymized_at = now; customer.updated_at = now
        _audit(db, store.id, customer.id, "anonymized", user, {"identity_count": len(visitor_ids)})
        db.commit()
        return {"anonymized": True, "customer_id": customer.id, "anonymized_at": now}
    except Exception:
        db.rollback()
        raise


@router.get("/conversations")
def list_conversations(
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(open|resolved|archived)$"),
    search: str | None = Query(default=None, max_length=200),
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    db: Session = Depends(get_db),
):
    _user, store = auth
    query = db.query(ChatSession).filter(ChatSession.store_id == store.id)
    if status: query = query.filter(ChatSession.status == status)
    else: query = query.filter(ChatSession.status != "archived")
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        customer_ids = db.query(Customer.id).filter(Customer.store_id == store.id, or_(func.lower(Customer.name).like(term), func.lower(Customer.email).like(term), func.lower(Customer.phone).like(term))).subquery()
        query = query.filter(or_(func.lower(ChatSession.visitor_id).like(term), ChatSession.customer_id.in_(customer_ids)))
    decoded = _decode_cursor(cursor)
    if decoded:
        ts, sid = decoded
        query = query.filter(or_(ChatSession.updated_at < ts, and_(ChatSession.updated_at == ts, ChatSession.id < sid)))
    rows = query.order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()).limit(limit + 1).all()
    next_cursor = _encode_cursor((rows[limit - 1].updated_at, rows[limit - 1].id)) if len(rows) > limit else None
    return {"items": [_conversation_row(db, s) for s in rows[:limit]], "next_cursor": next_cursor}


@router.post("/conversations/{conversation_id}/read")
def mark_read(
    conversation_id: str,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    session = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.conversation_key == conversation_id).with_for_update().first()
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    session.read_at = datetime.utcnow()
    _audit(db, store.id, session.customer_id, "conversation_read", user, conversation_id=session.id)
    db.commit()
    return {"conversation_id": conversation_id, "read_at": session.read_at, "unread": False}


@router.post("/conversations/{conversation_id}/status")
def set_conversation_status(
    conversation_id: str,
    payload: CustomerStatusRequest,
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, store = auth
    session = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.conversation_key == conversation_id).with_for_update().first()
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    now = datetime.utcnow()
    session.status = payload.status
    session.archived_at = now if payload.status == "archived" else None
    if payload.status in {"resolved", "archived"}: session.read_at = now
    _audit(db, store.id, session.customer_id, f"conversation_{payload.status}", user, conversation_id=session.id)
    db.commit(); db.refresh(session)
    return _conversation_row(db, session)


@router.get("/audit")
def list_audit(
    customer_id: str | None = None,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=100, ge=1, le=200),
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    db: Session = Depends(get_db),
):
    _user, store = auth
    query = db.query(CustomerAuditLog).filter(CustomerAuditLog.store_id == store.id)
    if customer_id: query = query.filter(CustomerAuditLog.customer_id == customer_id)
    decoded = _decode_cursor(cursor)
    if decoded:
        ts, aid = decoded
        query = query.filter(or_(CustomerAuditLog.created_at < ts, and_(CustomerAuditLog.created_at == ts, CustomerAuditLog.id < aid)))
    rows = query.order_by(CustomerAuditLog.created_at.desc(), CustomerAuditLog.id.desc()).limit(limit + 1).all()
    next_cursor = _encode_cursor((rows[limit - 1].created_at, rows[limit - 1].id)) if len(rows) > limit else None
    return {"items": [{"id": a.id, "customer_id": a.customer_id, "conversation_id": a.conversation_id, "action": a.action, "actor_type": a.actor_type, "actor_id": a.actor_id, "metadata": a.metadata_json, "created_at": a.created_at} for a in rows[:limit]], "next_cursor": next_cursor}
