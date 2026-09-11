from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.auth.models import APIKey
from app.auth.dashboard_auth import get_current_user_and_store
from app.core.tenant import get_current_store
from app.chat.models import ChatSession, ChatMessage
from app.db.database import get_db
from app.db.models import Store, User

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
        "mode_owner": session.mode_owner or "ai",
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


def _set_mode(session: ChatSession, mode: str, db: Session, owner: str = "merchant"):
    mode = mode.strip().lower()
    if mode not in {"ai", "human"}:
        raise HTTPException(status_code=400, detail="Mode must be 'ai' or 'human'")
    session.mode = mode
    session.mode_owner = "ai" if mode == "ai" else owner
    db.commit()
    db.refresh(session)
    return {
        "conversation_id": session.conversation_key,
        "mode": session.mode,
        "mode_owner": session.mode_owner,
    }


# Merchant-only endpoints intentionally use the dashboard JWT dependency.
# Never replace these with get_current_store(), because that dependency also
# accepts the public pk_live widget credential.
@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user_and_store)[0] if False else None,
):
    raise RuntimeError("unreachable")
