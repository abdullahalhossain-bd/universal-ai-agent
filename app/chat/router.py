from uuid import uuid4
import logging
import uuid
import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session

from app.chat.intelligent_service import IntelligentCommerceChatService
from app.chat.dynamic_service import DynamicAttributeChatService
from app.chat.models import ChatSession, ChatMessage
from app.chat.schemas import ChatRequest, ChatResponse
from app.core.rate_limit import enforce_rate_limit
from app.core.security import resolve_client_ip
from app.core.tenant import get_current_store
from app.db.agent_config import AgentConfig
from app.db.customer import Customer, CustomerIdentity
from app.db.database import get_db
from app.db.models import QueryEvent, Store
from app.db.visitor import VisitorProfile

router = APIRouter(prefix="/v1/chat", tags=["Chat"])
logger = logging.getLogger("app.chat.analytics")


def _log_query_event(db: Session, store_id: str, message: str, result: dict) -> None:
    try:
        products = (result.get("products") or []) if isinstance(result, dict) else []
        intent = (result.get("type") if isinstance(result, dict) else None) or ("product_search" if products else "general_question")
        db.add(QueryEvent(id=str(uuid.uuid4()), store_id=store_id, message=message[:500], intent=str(intent)[:30], matched_term=None, result_count=len(products), had_results=bool(products)))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to record chat analytics event for store %s", store_id, exc_info=True)


def _assistant_message_ids(db: Session, session_id: str) -> set[str]:
    rows = db.query(ChatMessage.id).filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant").all()
    return {str(row[0]) for row in rows}


def _discard_ai_after_takeover(db: Session, store_id: str, conversation_id: str, preexisting_assistant_ids: set[str]) -> bool:
    session = db.query(ChatSession).populate_existing().filter(ChatSession.store_id == store_id, ChatSession.conversation_key == conversation_id).first()
    if session is None or (session.mode or "ai") != "human": return False
    created = db.query(ChatMessage).filter(ChatMessage.session_id == session.id, ChatMessage.role == "assistant").all()
    stale = [message for message in created if str(message.id) not in preexisting_assistant_ids]
    if stale:
        for message in stale: db.delete(message)
        db.commit()
    return True


def _sync_customer(db: Session, store_id: str, session: ChatSession) -> Customer | None:
    """Attach a conversation to a first-class customer without treating anonymous as an identity."""
    visitor = (session.visitor_id or "").strip()
    if not visitor or visitor == "anonymous":
        return None
    identity = db.query(CustomerIdentity).filter(
        CustomerIdentity.store_id == store_id,
        CustomerIdentity.identity_type == "browser",
        CustomerIdentity.identity_value == visitor,
    ).first()
    customer = None
    if identity is not None:
        customer = db.query(Customer).filter(Customer.id == identity.customer_id, Customer.store_id == store_id).first()
    if customer is None:
        customer = Customer(store_id=store_id, customer_key=uuid.uuid4().hex)
        db.add(customer)
        db.flush()
        db.add(CustomerIdentity(store_id=store_id, customer_id=customer.id, identity_type="browser", identity_value=visitor))
    session.customer_id = customer.id
    customer.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return customer


def _sync_visitor_identity(db: Session, store_id: str, session: ChatSession, visitor_id: str | None) -> None:
    if not visitor_id: return
    visitor = visitor_id.strip()
    if not visitor: return
    if session.visitor_id != visitor:
        if session.visitor_id != "anonymous":
            raise HTTPException(status_code=409, detail="Visitor identity does not match this conversation")
        session.visitor_id = visitor
    profile = db.query(VisitorProfile).filter(VisitorProfile.store_id == store_id, VisitorProfile.visitor_id == visitor).first()
    if profile is None:
        db.add(VisitorProfile(store_id=store_id, visitor_id=visitor))
    db.commit()
    db.refresh(session)
    _sync_customer(db, store_id, session)


def _verify_conversation_token(session: ChatSession, supplied_token: str | None) -> None:
    if not supplied_token: raise HTTPException(status_code=401, detail="Conversation token required")
    expected = str(session.access_token or "")
    if not expected or not hmac.compare_digest(expected, supplied_token): raise HTTPException(status_code=403, detail="Invalid conversation token")


def _attach_conversation_token(result: dict, session: ChatSession | None) -> dict:
    if not isinstance(result, dict) or session is None: return result
    result["conversation_token"] = session.access_token
    return result


@router.post("", response_model=ChatResponse)
async def chat(http_request: Request, response: Response, request: ChatRequest, store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    client_ip = resolve_client_ip(peer_host=http_request.client.host if http_request.client else None, forwarded_for=http_request.headers.get("x-forwarded-for"))
    rate_limit = await enforce_rate_limit(store_id=store.id, plan=store.plan, client_ip=client_ip)
    ip_limit = rate_limit["ip"]
    response.headers["X-RateLimit-Limit"] = str(ip_limit["limit"])
    response.headers["X-RateLimit-Remaining"] = str(ip_limit["remaining"])
    response.headers["X-RateLimit-Reset"] = str(ip_limit["reset"])

    original_message = request.message.strip()
    conversation_id = request.conversation_id or uuid4().hex
    session = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.conversation_key == conversation_id).first()

    # Merchant dashboard requests are already authenticated by get_current_store()
    # with a validated Bearer JWT. Customer/storefront requests use the
    # conversation token because they authenticate with the public API key.
    dashboard_authenticated = (
        bool(http_request.headers.get("authorization"))
        and not bool(http_request.headers.get("x-api-key"))
    )
    if session is not None and not dashboard_authenticated:
        _verify_conversation_token(session, http_request.headers.get("x-conversation-token"))
        _sync_visitor_identity(db, store.id, session, request.visitor_id)

    if session is not None and (session.mode or "ai") == "human":
        service = DynamicAttributeChatService(db=db)
        service._save_message(session_id=session.id, role="user", content=original_message)
        result = {"conversation_id": conversation_id, "type": "manual", "message": "আপনার বার্তাটি আমাদের টিমের কাছে পাঠানো হয়েছে। একজন team member আপনাকে উত্তর দেবেন।", "products": [], "sources": []}
        _log_query_event(db, store.id, original_message, result)
        return _attach_conversation_token(result, session)

    config = db.query(AgentConfig).filter(AgentConfig.store_id == store.id).first()
    if config is not None and not config.auto_reply_enabled:
        service = DynamicAttributeChatService(db=db)
        session = service._get_or_create_session(store_id=store.id, conversation_id=conversation_id)
        if request.conversation_id and not dashboard_authenticated:
            _verify_conversation_token(session, http_request.headers.get("x-conversation-token"))
        _sync_visitor_identity(db, store.id, session, request.visitor_id)
        service._save_message(session_id=session.id, role="user", content=original_message)
        result = {"conversation_id": conversation_id, "type": "manual", "message": "ধন্যবাদ 😊 আপনার বার্তাটি আমাদের টিম পেয়েছে। একজন team member শিগগিরই উত্তর দেবেন।", "products": [], "sources": []}
        _log_query_event(db, store.id, original_message, result)
        return _attach_conversation_token(result, session)

    service = IntelligentCommerceChatService(db=db)
    preexisting_assistant_ids: set[str] = set()
    if session is not None: preexisting_assistant_ids = _assistant_message_ids(db, session.id)
    result = await service.handle(store_id=store.id, request=request)

    final_session = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.conversation_key == conversation_id).first()
    if final_session is not None:
        _sync_visitor_identity(db, store.id, final_session, request.visitor_id)
        _sync_customer(db, store.id, final_session)

    if conversation_id:
        takeover_won = _discard_ai_after_takeover(db=db, store_id=store.id, conversation_id=conversation_id, preexisting_assistant_ids=preexisting_assistant_ids)
        if takeover_won:
            manual_result = {"conversation_id": conversation_id, "type": "manual", "message": "আপনার বার্তাটি আমাদের টিমের কাছে পাঠানো হয়েছে। একজন team member আপনাকে উত্তর দেবেন।", "products": [], "sources": []}
            _log_query_event(db, store.id, original_message, manual_result)
            return _attach_conversation_token(manual_result, final_session)

    if isinstance(result, dict) and not result.get("interaction_id"): _log_query_event(db, store.id, original_message, result)
    return _attach_conversation_token(result, final_session)
