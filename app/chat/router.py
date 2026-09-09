from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Store
from app.db.agent_config import AgentConfig
from app.core.security import resolve_client_ip
from app.core.rate_limit import enforce_rate_limit
from app.core.tenant import get_current_store
from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.dynamic_service import DynamicAttributeChatService

router = APIRouter(prefix="/v1/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
async def chat(http_request: Request, response: Response, request: ChatRequest, store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    client_ip = resolve_client_ip(peer_host=http_request.client.host if http_request.client else None, forwarded_for=http_request.headers.get("x-forwarded-for"))
    rate_limit = await enforce_rate_limit(store_id=store.id, plan=store.plan, client_ip=client_ip)
    ip_limit = rate_limit["ip"]
    response.headers["X-RateLimit-Limit"] = str(ip_limit["limit"])
    response.headers["X-RateLimit-Remaining"] = str(ip_limit["remaining"])
    response.headers["X-RateLimit-Reset"] = str(ip_limit["reset"])

    config = db.query(AgentConfig).filter(AgentConfig.store_id == store.id).first()
    if config is not None and not config.auto_reply_enabled:
        service = DynamicAttributeChatService(db=db)
        conversation_id = request.conversation_id or __import__("uuid").uuid4().hex
        session = service._get_or_create_session(store_id=store.id, conversation_id=conversation_id)
        service._save_message(session_id=session.id, role="user", content=request.message.strip())
        return {
            "conversation_id": conversation_id,
            "type": "manual",
            "message": "Thanks! A member of the store team will reply shortly.",
            "products": [],
            "sources": [],
        }

    service = DynamicAttributeChatService(db=db)
    return await service.handle(store_id=store.id, request=request)
