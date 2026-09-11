from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.auth.models import APIKey
from app.core.tenant import get_current_store
from app.chat.models import ChatSession, ChatMessage
from app.db.database import get_db
from app.db.models import Store

router = APIRouter(prefix="/v1/messages", tags=["messages"])


class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class CustomerMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    visitor_id: str = Field(default="anonymous", min_length=1, max_length=100)


class ModeRequest(BaseModel):
    mode: str = Field(min_length=2, max_length=20)


def _message_row(message: ChatMessage):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }


def _conversation_row(session: ChatSession, messages: list[ChatMessage]):
    last = messages[-1] if messages else None
    return {
        "conversation_id": session.conversation_key,
        "session_id": session.id,
        "visitor_id": session.visitor_id,
        "mode": session.mode or "ai",
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "last_message": _message_row(last) if last else None,
        "messages": [_message_row(item) for item in messages],
    }


def _authorized_customer(api_key: APIKey, x_api_key: str | None) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if api_key.store_id is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key.store_id


def _find_session(db: Session, store_id: str, conversation_id: str):
    return (
        db.query(ChatSession)
        .filter(
            ChatSession.store_id == store_id,
            ChatSession.conversation_key == conversation_id,
        )
        .first()
    )


def _set_mode(session: ChatSession, mode: str, db: Session):
    mode = mode.strip().lower()
    if mode not in {"ai", "human"}:
        raise HTTPException(status_code=400, detail="Mode must be 'ai' or 'human'")
    session.mode = mode
    db.commit()
    db.refresh(session)
    return {"conversation_id": session.conversation_key, "mode": session.mode}


@router.get("/conversations")
def list_conversations(
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.store_id == store.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
        .all()
    )
    result = []
    for session in sessions:
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        result.append({
            "conversation_id": session.conversation_key,
            "session_id": session.id,
            "visitor_id": session.visitor_id,
            "mode": session.mode or "ai",
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_message": _message_row(last) if last else None,
        })
    return result


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    session = _find_session(db, store.id, conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session.id,
            ChatMessage.role.in_(["user", "assistant", "merchant"]),
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return _conversation_row(session, messages)


@router.post("/conversations/{conversation_id}/mode")
def merchant_set_mode(
    conversation_id: str,
    payload: ModeRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    session = _find_session(db, store.id, conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _set_mode(session, payload.mode, db)


@router.post("/conversations/{conversation_id}/reply")
def merchant_reply(
    conversation_id: str,
    payload: ReplyRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    session = _find_session(db, store.id, conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # A merchant reply is an explicit human takeover. The AI pipeline must
    # stay disabled for this conversation until mode is switched back to AI.
    session.mode = "human"
    message = ChatMessage(
        session_id=session.id,
        role="merchant",
        content=payload.message.strip(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_row(message)


@router.get("/customer/{conversation_id}")
def customer_messages(
    conversation_id: str,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    store_id = _authorized_customer(api_key, x_api_key)
    session = _find_session(db, store_id, conversation_id)
    if session is None:
        return {"conversation_id": conversation_id, "mode": "ai", "messages": []}
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session.id,
            ChatMessage.role.in_(["assistant", "merchant"]),
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {
        "conversation_id": conversation_id,
        "mode": session.mode or "ai",
        "messages": [_message_row(item) for item in messages],
    }


@router.post("/customer/{conversation_id}/mode")
def customer_set_mode(
    conversation_id: str,
    payload: ModeRequest,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    store_id = _authorized_customer(api_key, x_api_key)
    conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid conversation id")

    session = _find_session(db, store_id, conversation_id)
    if session is None:
        session = ChatSession(
            store_id=store_id,
            conversation_key=conversation_id,
            visitor_id="anonymous",
            mode="ai",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    return _set_mode(session, payload.mode, db)


@router.post("/customer/{conversation_id}")
def customer_message(
    conversation_id: str,
    payload: CustomerMessageRequest,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Store a customer message for a human merchant conversation.

    This endpoint intentionally does not invoke the AI pipeline. It switches
    the conversation to human mode so subsequent /v1/chat calls are blocked
    from generating automatic AI replies until the mode is returned to AI.
    """
    store_id = _authorized_customer(api_key, x_api_key)
    conversation_id = conversation_id.strip()
    if not conversation_id or len(conversation_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid conversation id")

    session = _find_session(db, store_id, conversation_id)
    if session is None:
        session = ChatSession(
            store_id=store_id,
            conversation_key=conversation_id,
            visitor_id=payload.visitor_id.strip() or "anonymous",
            mode="human",
        )
        db.add(session)
        db.flush()
    else:
        session.mode = "human"

    message = ChatMessage(
        session_id=session.id,
        role="user",
        content=payload.message.strip(),
    )
    db.add(message)
    session.visitor_id = payload.visitor_id.strip() or session.visitor_id or "anonymous"
    db.commit()
    db.refresh(message)
    return _message_row(message)
