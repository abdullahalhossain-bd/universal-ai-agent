from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.auth.dependency import authenticate_api_key
from app.auth.models import APIKey
from app.db.database import get_db
from app.db.models import Store
from app.db.agent_config import AgentConfig
from app.core.security import resolve_client_ip
from app.core.rate_limit import enforce_rate_limit
from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.service import ChatService

router = APIRouter(prefix="/v1/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
async def chat(http_request: Request, response: Response, request: ChatRequest, api_key: APIKey = Depends(authenticate_api_key), db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == api_key.store_id).first()
    if store is None:
        raise HTTPException(status_code=401, detail="Store not found")
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="This store has been suspended. Contact support.")

    client_ip = resolve_client_ip(peer_host=http_request.client.host if http_request.client else None, forwarded_for=http_request.headers.get("x-forwarded-for"))
    rate_limit = await enforce_rate_limit(store_id=store.id, plan=store.plan, client_ip=client_ip)
    ip_limit = rate_limit["ip"]
    response.headers["X-RateLimit-Limit"] = str(ip_limit["limit"])
    response.headers["X-RateLimit-Remaining"] = str(ip_limit["remaining"])
    response.headers["X-RateLimit-Reset"] = str(ip_limit["reset"])

    config = db.query(AgentConfig).filter(AgentConfig.store_id == store.id).first()
    if config is not None and not config.auto_reply_enabled:
        service = ChatService(db=db)
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

    service = ChatService(db=db)
    return await service.handle(store_id=store.id, request=request)
