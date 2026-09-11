from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.auth.models import APIKey
from app.auth.inbox_auth import get_current_inbox_user_and_store, require_inbox_csrf
from app.chat.models import ChatSession, ChatMessage
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

def _message_row(message: ChatMessage):
    return {"id": message.id, "role": message.role, "content": message.content, "created_at": message.created_at}

def _profile_row(profile: VisitorProfile | None):
    if profile is None:
        return {"visitor_id": None, "name": None, "email": None, "phone": None}
    return {"visitor_id": profile.visitor_id, "name": profile.name, "email": profile.email, "phone": profile.phone}

def _get_profile(db: Session, store_id: str, visitor_id: str):
    return db.query(VisitorProfile).filter(VisitorProfile.store_id == store_id, VisitorProfile.visitor_id == visitor_id).first()

def _upsert_profile(db: Session, store_id: str, visitor_id: str, name=None, email=None, phone=None):
    visitor_id = (visitor_id or "anonymous").strip() or "anonymous"
    profile = _get_profile(db, store_id, visitor_id)
    if profile is None:
        profile = VisitorProfile(store_id=store_id, visitor_id=visitor_id)
        db.add(profile)
    if name is not None:
        value = name.strip()
        if value: profile.name = value
    if email is not None:
        profile.email = str(email).strip().lower()
    if phone is not None:
        value = phone.strip()
        if value: profile.phone = value
    return profile

def _conversation_identity(db: Session, session: ChatSession):
    return _profile_row(_get_profile(db, session.store_id, session.visitor_id))

def _conversation_row(session: ChatSession, messages: list[ChatMessage], db: Session):
    last = messages[-1] if messages else None
    return {"conversation_id": session.conversation_key, "session_id": session.id, "visitor_id": session.visitor_id, "identity": _conversation_identity(db, session), "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "created_at": session.created_at, "updated_at": session.updated_at, "last_message": _message_row(last) if last else None, "messages": [_message_row(item) for item in messages]}

def _authorized_customer(api_key: APIKey, x_api_key: str | None) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if api_key.store_id is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key.store_id

def _find_session(db: Session, store_id: str, conversation_id: str):
    return db.query(ChatSession).filter(ChatSession.store_id == store_id, ChatSession.conversation_key == conversation_id).first()

def _set_mode(session: ChatSession, mode: str, db: Session, owner: str = "merchant"):
    mode = mode.strip().lower()
    if mode not in {"ai", "human"}:
        raise HTTPException(status_code=400, detail="Mode must be 'ai' or 'human'")
    session.mode = mode
    session.mode_owner = "ai" if mode == "ai" else owner
    db.commit(); db.refresh(session)
    return {"conversation_id": session.conversation_key, "mode": session.mode, "mode_owner": session.mode_owner}

# Merchant Inbox endpoints are intentionally cookie-session-only. Public pk_live credentials are never accepted by these routes.
@router.get("/conversations")
def list_conversations(auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    sessions = db.query(ChatSession).filter(ChatSession.store_id == store.id).order_by(ChatSession.updated_at.desc()).limit(100).all()
    result = []
    for session in sessions:
        last = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.desc()).first()
        result.append({"conversation_id": session.conversation_key, "session_id": session.id, "visitor_id": session.visitor_id, "identity": _conversation_identity(db, session), "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "created_at": session.created_at, "updated_at": session.updated_at, "last_message": _message_row(last) if last else None})
    return result

@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store), db: Session = Depends(get_db)):
    _user, store = auth
    session = _find_session(db, store.id, conversation_id)
    if session is None: raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id, ChatMessage.role.in_(["user", "assistant", "merchant"])).order_by(ChatMessage.created_at.asc()).all()
    return _conversation_row(session, messages, db)

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
    session.mode = "human"; session.mode_owner = "merchant"
    message = ChatMessage(session_id=session.id, role="merchant", content=payload.message.strip())
    db.add(message); db.commit(); db.refresh(message)
    return _message_row(message)

# Public widget/customer endpoints intentionally remain pk_live-only.
@router.get("/customer/{conversation_id}")
def customer_messages(conversation_id: str, x_api_key: str | None = Header(default=None, alias="x-api-key"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key)
    session = _find_session(db, store_id, conversation_id)
    if session is None:
        return {"conversation_id": conversation_id, "mode": "ai", "mode_owner": "ai", "identity": _profile_row(None), "messages": []}
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id, ChatMessage.role.in_(["assistant", "merchant"])).order_by(ChatMessage.created_at.asc()).all()
    return {"conversation_id": conversation_id, "mode": session.mode or "ai", "mode_owner": session.mode_owner or "ai", "identity": _conversation_identity(db, session), "messages": [_message_row(item) for item in messages]}

@router.post("/customer/{conversation_id}/mode")
def customer_set_mode(conversation_id: str, payload: ModeRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key)
    conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    session = _find_session(db, store_id, conversation_id)
    if session is None:
        session = ChatSession(store_id=store_id, conversation_key=conversation_id, visitor_id="anonymous", mode="ai", mode_owner="ai")
        db.add(session); db.commit(); db.refresh(session)
    requested = payload.mode.strip().lower()
    if requested == "ai" and session.mode_owner == "merchant": raise HTTPException(status_code=409, detail="The merchant currently controls this conversation. Only the merchant can resume AI.")
    if requested == "human": return _set_mode(session, "human", db, owner="customer")
    return _set_mode(session, "ai", db, owner="customer")

@router.post("/customer/{conversation_id}/identity")
def customer_identity(conversation_id: str, payload: CustomerIdentityRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key)
    conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    session = _find_session(db, store_id, conversation_id)
    if session is None:
        session = ChatSession(store_id=store_id, conversation_key=conversation_id, visitor_id=payload.visitor_id.strip() or "anonymous", mode="ai", mode_owner="ai")
        db.add(session); db.flush()
    elif session.visitor_id != payload.visitor_id.strip():
        raise HTTPException(status_code=409, detail="Visitor identity does not match this conversation")
    profile = _upsert_profile(db, store_id, session.visitor_id, payload.name, payload.email, payload.phone)
    db.commit(); db.refresh(profile)
    return {"conversation_id": conversation_id, "identity": _profile_row(profile)}

@router.post("/customer/{conversation_id}")
def customer_message(conversation_id: str, payload: CustomerMessageRequest, x_api_key: str | None = Header(default=None, alias="x-api-key"), api_key: APIKey = Depends(get_api_key), db: Session = Depends(get_db)):
    store_id = _authorized_customer(api_key, x_api_key)
    conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200: raise HTTPException(status_code=400, detail="Invalid conversation id")
    visitor = payload.visitor_id.strip() or "anonymous"
    session = _find_session(db, store_id, conversation_id)
    if session is None:
        session = ChatSession(store_id=store_id, conversation_key=conversation_id, visitor_id=visitor, mode="human", mode_owner="customer")
        db.add(session); db.flush()
    else:
        if session.visitor_id != visitor:
            raise HTTPException(status_code=409, detail="Visitor identity does not match this conversation")
        session.mode = "human"
        if session.mode_owner != "merchant": session.mode_owner = "customer"
    _upsert_profile(db, store_id, session.visitor_id, payload.name, payload.email, payload.phone)
    message = ChatMessage(session_id=session.id, role="user", content=payload.message.strip())
    db.add(message)
    db.commit(); db.refresh(message)
    return _message_row(message)
