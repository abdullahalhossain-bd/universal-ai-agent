from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.auth.models import APIKey
from app.auth.inbox_auth import get_current_inbox_user_and_store, require_inbox_csrf
from app.chat.models import ChatSession, ChatMessage
from app.db.customer import Customer, CustomerIdentity, CustomerIdentityHistory
from app.db.database import get_db
from app.db.models import Store, User
from app.db.visitor import VisitorProfile

router = APIRouter(prefix="/v1/messages", tags=["messages"])

class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class CustomerMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    visitor_id: str = Field(default="anonymous", min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

class ModeRequest(BaseModel):
    mode: str = Field(min_length=2, max_length=20)

class CustomerIdentityRequest(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

class CustomerMergeRequest(BaseModel):
    source_customer_id: str = Field(min_length=36, max_length=36)
    target_customer_id: str = Field(min_length=36, max_length=36)


def _message_row(message: ChatMessage):
    return {"id": message.id, "role": message.role, "content": message.content, "created_at": message.created_at}


def _profile_row(profile: VisitorProfile | None):
    if profile is None:
        return {"visitor_id": None, "name": None, "email": None, "phone": None}
    return {"visitor_id": profile.visitor_id, "name": profile.name, "email": profile.email, "phone": profile.phone}


def _customer_row(customer: Customer | None):
    if customer is None:
        return {"customer_id": None, "name": None, "email": None, "phone": None, "first_seen_at": None, "last_seen_at": None, "merged_into_customer_id": None}
    return {"customer_id": customer.id, "name": customer.name, "email": customer.email, "phone": customer.phone, "first_seen_at": customer.first_seen_at, "last_seen_at": customer.last_seen_at, "merged_into_customer_id": customer.merged_into_customer_id}


def _get_profile(db: Session, store_id: str, visitor_id: str):
    return db.query(VisitorProfile).filter(VisitorProfile.store_id == store_id, VisitorProfile.visitor_id == visitor_id).first()


def _get_customer(db: Session, store_id: str, customer_id: str):
    return db.query(Customer).filter(Customer.store_id == store_id, Customer.id == customer_id).first()


def _upsert_profile(db: Session, store_id: str, visitor_id: str, name=None, email=None, phone=None):
    visitor_id = (visitor_id or "anonymous").strip() or "anonymous"
    profile = _get_profile(db, store_id, visitor_id)
    if profile is None:
        profile = VisitorProfile(store_id=store_id, visitor_id=visitor_id)
        db.add(profile)
    if name is not None and name.strip(): profile.name = name.strip()
    if email is not None: profile.email = str(email).strip().lower()
    if phone is not None and phone.strip(): profile.phone = phone.strip()
    return profile


def _sync_customer_profile(db: Session, session: ChatSession, name=None, email=None, phone=None, actor_type="customer", actor_id=None):
    if not session.customer_id:
        return None
    customer = _get_customer(db, session.store_id, session.customer_id)
    if customer is None or customer.merged_into_customer_id:
        return None
    if isinstance(name, str) and name.strip(): customer.name = name.strip()
    customer.last_seen_at = datetime.utcnow()
    customer.updated_at = datetime.utcnow()
    return customer


def _sync_customer_from_profile(db: Session, session: ChatSession):
    if not session.customer_id or session.visitor_id == "anonymous": return None
    customer = _get_customer(db, session.store_id, session.customer_id)
    if customer is None or customer.merged_into_customer_id: return None
    profile = _get_profile(db, session.store_id, session.visitor_id)
    if profile and profile.name and not customer.name: customer.name = profile.name
    customer.last_seen_at = datetime.utcnow()
    return customer


def _conversation_identity(db: Session, session: ChatSession):
    customer = _sync_customer_from_profile(db, session)
    if customer: return {**_customer_row(customer), "visitor_id": session.visitor_id}
    return {**_profile_row(_get_profile(db, session.store_id, session.visitor_id)), "customer_id": None}


def _conversation_row(session: ChatSession, messages: list[ChatMessage], db: Session):
    last = messages[-1] if messages else None
    return {"conversation_id": session.conversation_key, "session_id": session.id, "visitor_id": session.visitor_id, "customer_id": session.customer_id, "identity": _conversation_identity(db, session), "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "status": session.status or "open", "created_at": session.created_at, "updated_at": session.updated_at, "last_message": _message_row(last) if last else None, "messages": [_message_row(item) for item in messages]}


def _authorized_customer(api_key: APIKey, x_api_key: str | None) -> str:
    if not x_api_key: raise HTTPException(status_code=401, detail="API key required")
    if api_key.store_id is None: raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key.store_id


def _find_session(db: Session, store_id: str, conversation_id: str):
    return db.query(ChatSession).filter(ChatSession.store_id == store_id, ChatSession.conversation_key == conversation_id).first()


def _require_customer_conversation(session: ChatSession, conversation_token: str | None) -> None:
    if not conversation_token: raise HTTPException(status_code=401, detail="Conversation token required")
    if not session.access_token or not secrets_compare(session.access_token, conversation_token): raise HTTPException(status_code=403, detail="Invalid conversation token")


def secrets_compare(expected: str, provided: str) -> bool:
    import hmac
    return hmac.compare_digest(str(expected), str(provided))


def _set_mode(session: ChatSession, mode: str, db: Session, owner: str = "merchant"):
    mode = mode.strip().lower()
    if mode not in {"ai", "human"}: raise HTTPException(status_code=400, detail="Mode must be 'ai' or 'human'")
    session.mode = mode; session.mode_owner = "ai" if mode == "ai" else owner
    db.commit(); db.refresh(session)
    return {"conversation_id": session.conversation_key, "mode": session.mode, "mode_owner": session.mode_owner}


@router.get("/conversations")
def list_conversations(auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    sessions = db.query(ChatSession).filter(ChatSession.store_id == store.id).order_by(ChatSession.updated_at.desc()).limit(100).all()
    result = []
    for session in sessions:
        last = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.desc()).first()
        result.append({"conversation_id": session.conversation_key, "session_id": session.id, "visitor_id": session.visitor_id, "customer_id": session.customer_id, "identity": _conversation_identity(db, session), "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "status": session.status or "open", "created_at": session.created_at, "updated_at": session.updated_at, "last_message": _message_row(last) if last else None})
    db.commit()
    return result


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    session = _find_session(db, store.id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id, ChatMessage.role.in_(["user", "assistant", "merchant"])).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
    return _conversation_row(session, messages, db)


@router.get("/customers")
def list_customers(search: str | None = Query(default=None, max_length=200), auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    query = db.query(Customer).filter(Customer.store_id == store.id, Customer.merged_into_customer_id.is_(None))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(or_(func.lower(Customer.name).like(term), func.lower(Customer.email).like(term), func.lower(Customer.phone).like(term), Customer.id.like(f"%{search.strip()}%")))
    return [_customer_row(c) for c in query.order_by(Customer.last_seen_at.desc()).limit(50).all()]


@router.get("/customers/{customer_id}")
def get_customer_profile(customer_id: str, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    customer = _get_customer(db, store.id, customer_id)
    if customer is None: raise HTTPException(status_code=404, detail="Customer not found")
    if customer.merged_into_customer_id: raise HTTPException(status_code=409, detail=f"Customer was merged into {customer.merged_into_customer_id}")
    identities = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == customer.id).order_by(CustomerIdentity.created_at.asc()).all()
    conversations = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.customer_id == customer.id).order_by(ChatSession.updated_at.desc()).limit(100).all()
    history = db.query(CustomerIdentityHistory).filter(CustomerIdentityHistory.store_id == store.id, CustomerIdentityHistory.customer_id == customer.id).order_by(CustomerIdentityHistory.created_at.desc()).limit(100).all()
    return {"customer": _customer_row(customer), "identities": [{"id": i.id, "type": i.identity_type, "value": i.identity_value, "created_at": i.created_at, "updated_at": i.updated_at} for i in identities], "conversations": [{"conversation_id": s.conversation_key, "session_id": s.id, "updated_at": s.updated_at, "mode": s.mode or "ai", "status": s.status or "open"} for s in conversations], "identity_history": [{"id": h.id, "action": h.action, "identity_type": h.identity_type, "identity_value": h.identity_value, "from_customer_id": h.from_customer_id, "to_customer_id": h.to_customer_id, "actor_type": h.actor_type, "actor_id": h.actor_id, "metadata": h.metadata_json, "created_at": h.created_at} for h in history]}


@router.post("/customers/merge")
def merge_customers(payload: CustomerMergeRequest, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), _csrf: None = Depends(require_inbox_csrf), db: Session = Depends(get_db)):
    user, store = auth
    if payload.source_customer_id == payload.target_customer_id: raise HTTPException(status_code=400, detail="Source and target customer must be different")
    source = _get_customer(db, store.id, payload.source_customer_id); target = _get_customer(db, store.id, payload.target_customer_id)
    if source is None or target is None: raise HTTPException(status_code=404, detail="Source or target customer not found")
    if source.merged_into_customer_id: raise HTTPException(status_code=409, detail="Source customer is already merged")
    if target.merged_into_customer_id: raise HTTPException(status_code=409, detail="Target customer is already merged")
    now = datetime.utcnow()
    db.add(CustomerIdentityHistory(store_id=store.id, customer_id=target.id, action="merge_started", from_customer_id=source.id, to_customer_id=target.id, actor_type="merchant", actor_id=user.id, metadata_json={"source_customer_id": source.id, "target_customer_id": target.id}, created_at=now))
    for identity in db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == source.id).all():
        duplicate = db.query(CustomerIdentity).filter(CustomerIdentity.store_id == store.id, CustomerIdentity.customer_id == target.id, CustomerIdentity.identity_type == identity.identity_type, CustomerIdentity.identity_value == identity.identity_value).first()
        identity_value = identity.identity_value; identity_type = identity.identity_type
        if duplicate: db.delete(identity); action = "identity_deduplicated"
        else: identity.customer_id = target.id; identity.updated_at = now; action = "identity_moved"
        db.add(CustomerIdentityHistory(store_id=store.id, customer_id=target.id, action=action, identity_type=identity_type, identity_value=identity_value, from_customer_id=source.id, to_customer_id=target.id, actor_type="merchant", actor_id=user.id, created_at=now))
    for session in db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.customer_id == source.id).all(): session.customer_id = target.id
    for field in ("name", "email", "phone"):
        if not getattr(target, field) and getattr(source, field): setattr(target, field, getattr(source, field))
    target.first_seen_at = min(target.first_seen_at, source.first_seen_at); target.last_seen_at = max(target.last_seen_at, source.last_seen_at); target.updated_at = now
    source.merged_into_customer_id = target.id; source.updated_at = now
    db.add(CustomerIdentityHistory(store_id=store.id, customer_id=target.id, action="merged", from_customer_id=source.id, to_customer_id=target.id, actor_type="merchant", actor_id=user.id, metadata_json={"source_customer_id": source.id, "target_customer_id": target.id}, created_at=now))
    db.commit(); db.refresh(target)
    return {"merged": True, "customer": _customer_row(target), "source_customer_id": source.id, "target_customer_id": target.id}


@router.post("/conversations/{conversation_id}/mode")
def merchant_set_mode(conversation_id: str, payload: ModeRequest, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), _csrf: None = Depends(require_inbox_csrf), db: Session = Depends(get_db)):
    _user, store = auth
    session = _find_session(db, store.id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    return _set_mode(session, payload.mode, db, owner="merchant")


@router.post("/conversations/{conversation_id}/reply")
def merchant_reply(conversation_id: str, payload: ReplyRequest, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), _csrf: None = Depends(require_inbox_csrf), db: Session = Depends(get_db)):
    _user, store = auth
    session = _find_session(db, store.id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    session.mode = "human"; session.mode_owner = "merchant"; session.status = "open"
    message = ChatMessage(session_id=session.id, role="merchant", content=payload.message.strip())
    db.add(message); db.commit(); db.refresh(message)
    return _message_row(message)


@router.get("/customer/{conversation_id}")
def customer_messages(conversation_id: str, after_id: str | None = None, x_api_key: str | None = Header(default=None, alias="x-api-key"), x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key); session = _find_session(db, store_id, conversation_id)
    if session is None: return {"conversation_id": conversation_id, "mode": "ai", "mode_owner": "ai", "identity": _profile_row(None), "messages": []}
    _require_customer_conversation(session, x_conversation_token)
    query = db.query(ChatMessage).filter(ChatMessage.session_id == session.id, ChatMessage.role.in_(["assistant", "merchant"]))
    if after_id is not None:
        cursor = db.query(ChatMessage.created_at).filter(ChatMessage.id == after_id, ChatMessage.session_id == session.id).scalar()
        if cursor is not None:
            # UUIDs are not chronological, but they are a stable deterministic
            # tie-breaker for messages sharing the same timestamp. Using both
            # columns prevents same-timestamp rows from being skipped.
            query = query.filter(or_(ChatMessage.created_at > cursor, and_(ChatMessage.created_at == cursor, ChatMessage.id > after_id)))
    messages = query.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
    return {"conversation_id": conversation_id, "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "identity": _conversation_identity(db, session), "messages": [_message_row(item) for item in messages]}


@router.post("/customer/{conversation_id}/mode")
def customer_set_mode(conversation_id: str, payload: ModeRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key); conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    session = _find_session(db, store_id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    _require_customer_conversation(session, x_conversation_token); requested = payload.mode.strip().lower()
    if requested == "ai" and session.mode_owner == "merchant": raise HTTPException(status_code=409, detail="The merchant currently controls this conversation. Only the merchant can resume AI.")
    return _set_mode(session, "human", db, owner="customer") if requested == "human" else _set_mode(session, "ai", db, owner="customer")


@router.post("/customer/{conversation_id}/identity")
def customer_identity(conversation_id: str, payload: CustomerIdentityRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key); conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    session = _find_session(db, store_id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    _require_customer_conversation(session, x_conversation_token)
    if session.visitor_id != payload.visitor_id.strip(): raise HTTPException(status_code=409, detail="Visitor identity does not match this conversation")
    profile = _upsert_profile(db, store_id, session.visitor_id, payload.name, payload.email, payload.phone)
    customer = _sync_customer_profile(db, session, payload.name, None, None, actor_type="customer")
    db.commit(); db.refresh(profile)
    return {"conversation_id": conversation_id, "customer_id": customer.id if customer else None, "identity": {**_profile_row(profile), **_customer_row(customer)}, "trusted_email_phone_linked": False}


@router.post("/customer/{conversation_id}")
def customer_message(conversation_id: str, payload: CustomerMessageRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key); conversation_id = conversation_id.strip(); visitor = payload.visitor_id.strip() or "anonymous"
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    session = _find_session(db, store_id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    _require_customer_conversation(session, x_conversation_token)
    if session.visitor_id != visitor: raise HTTPException(status_code=409, detail="Visitor identity does not match this conversation")
    session.mode = "human"
    if session.mode_owner != "merchant": session.mode_owner = "customer"
    session.status = "open"; session.read_at = None
    _upsert_profile(db, store_id, session.visitor_id, payload.name, payload.email, payload.phone)
    _sync_customer_profile(db, session, payload.name, None, None, actor_type="customer")
    message = ChatMessage(session_id=session.id, role="user", content=payload.message.strip()); db.add(message); session.updated_at = datetime.utcnow(); db.commit(); db.refresh(message)
    return _message_row(message)
