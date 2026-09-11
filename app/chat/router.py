from uuid import uuid4
import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.chat.intelligent_service import IntelligentCommerceChatService
from app.chat.dynamic_service import DynamicAttributeChatService
from app.chat.models import ChatSession, ChatMessage
from app.chat.schemas import ChatRequest, ChatResponse
from app.core.rate_limit import enforce_rate_limit
from app.core.security import resolve_client_ip
from app.core.tenant import get_current_store
from app.db.agent_config import AgentConfig
from app.db.database import get_db
from app.db.models import QueryEvent, Store

router = APIRouter(prefix="/v1/chat", tags=["Chat"])
logger = logging.getLogger("app.chat.analytics")


def _log_query_event(db: Session, store_id: str, message: str, result: dict) -> None:
    """Record a query only for chat branches that did not already log one."""
    try:
        products = (result.get("products") or []) if isinstance(result, dict) else []
        intent = (result.get("type") if isinstance(result, dict) else None) or ("product_search" if products else "general_question")
        db.add(QueryEvent(
            id=str(uuid.uuid4()),
            store_id=store_id,
            message=message[:500],
            intent=str(intent)[:30],
            matched_term=None,
            result_count=len(products),
            had_results=bool(products),
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to record chat analytics event for store %s", store_id, exc_info=True)


def _assistant_message_ids(db: Session, session_id: str) -> set[str]:
    """Snapshot assistant messages before an AI request starts."""
    rows = (
        db.query(ChatMessage.id)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
        )
        .all()
    )
    return {str(row[0]) for row in rows}


def _discard_ai_after_takeover(
    db: Session,
    store_id: str,
    conversation_id: str,
    preexisting_assistant_ids: set[str],
) -> bool:
    """Make a committed human takeover authoritative over in-flight AI.

    The session row is refreshed from the database because the same SQLAlchemy
    Session may already have an identity-mapped ChatSession from the AI call.
    Without populate_existing(), a concurrent merchant takeover could remain
    invisible to this request until the request ends.
    """
    session = (
        db.query(ChatSession)
        .populate_existing()
        .filter(
            ChatSession.store_id == store_id,
            ChatSession.conversation_key == conversation_id,
        )
        .first()
    )
    if session is None or (session.mode or "ai") != "human":
        return False

    created = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session.id,
            ChatMessage.role == "assistant",
        )
        .all()
    )
    stale = [
        message for message in created
        if str(message.id) not in preexisting_assistant_ids
    ]
    if stale:
        for message in stale:
            db.delete(message)
        db.commit()
    return True


@router.post("", response_model=ChatResponse)
async def chat(
    http_request: Request,
    response: Response,
    request: ChatRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    client_ip = resolve_client_ip(
        peer_host=http_request.client.host if http_request.client else None,
        forwarded_for=http_request.headers.get("x-forwarded-for"),
    )
    rate_limit = await enforce_rate_limit(
        store_id=store.id,
        plan=store.plan,
        client_ip=client_ip,
    )
    ip_limit = rate_limit["ip"]
    response.headers["X-RateLimit-Limit"] = str(ip_limit["limit"])
    response.headers["X-RateLimit-Remaining"] = str(ip_limit["remaining"])
    response.headers["X-RateLimit-Reset"] = str(ip_limit["reset"])

    original_message = request.message.strip()
    conversation_id = request.conversation_id or uuid4().hex

    # Per-conversation human takeover has higher priority than the global
    # auto-reply setting. Once a merchant/customer explicitly switches a
    # conversation to human mode, /v1/chat must not invoke the AI pipeline.
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.store_id == store.id,
            ChatSession.conversation_key == conversation_id,
        )
        .first()
    )
    if session is not None and (session.mode or "ai") == "human":
        service = DynamicAttributeChatService(db=db)
        service._save_message(session_id=session.id, role="user", content=original_message)
        result = {
            "conversation_id": conversation_id,
            "type": "manual",
            "message": "আপনার বার্তাটি আমাদের টিমের কাছে পাঠানো হয়েছে। একজন team member আপনাকে উত্তর দেবেন।",
            "products": [],
            "sources": [],
        }
        _log_query_event(db, store.id, original_message, result)
        return result

    config = db.query(AgentConfig).filter(AgentConfig.store_id == store.id).first()
    if config is not None and not config.auto_reply_enabled:
        service = DynamicAttributeChatService(db=db)
        session = service._get_or_create_session(store_id=store.id, conversation_id=conversation_id)
        service._save_message(session_id=session.id, role="user", content=original_message)
        result = {
            "conversation_id": conversation_id,
            "type": "manual",
            "message": "ধন্যবাদ 😊 আপনার বার্তাটি আমাদের টিম পেয়েছে। একজন team member শিগগিরই আপনাকে উত্তর দেবেন।",
            "products": [],
            "sources": [],
        }
        _log_query_event(db, store.id, original_message, result)
        return result

    service = IntelligentCommerceChatService(db=db)
    preexisting_assistant_ids: set[str] = set()
    if session is not None:
        preexisting_assistant_ids = _assistant_message_ids(db, session.id)
    else:
        existing_session = (
            db.query(ChatSession)
            .filter(
                ChatSession.store_id == store.id,
                ChatSession.conversation_key == conversation_id,
            )
            .first()
        )
        if existing_session is not None:
            preexisting_assistant_ids = _assistant_message_ids(db, existing_session.id)

    result = await service.handle(store_id=store.id, request=request)

    # A merchant may take over while the LLM is still generating. The initial
    # mode check above cannot close that race because AI generation is slow.
    # Re-check after generation and suppress any assistant messages produced
    # during this request if human mode has won in the meantime.
    if conversation_id:
        takeover_won = _discard_ai_after_takeover(
            db=db,
            store_id=store.id,
            conversation_id=conversation_id,
            preexisting_assistant_ids=preexisting_assistant_ids,
        )
        if takeover_won:
            manual_result = {
                "conversation_id": conversation_id,
                "type": "manual",
                "message": "আপনার বার্তাটি আমাদের টিমের কাছে পাঠানো হয়েছে। একজন team member আপনাকে উত্তর দেবেন।",
                "products": [],
                "sources": [],
            }
            _log_query_event(db, store.id, original_message, manual_result)
            return manual_result

    if isinstance(result, dict) and not result.get("interaction_id"):
        _log_query_event(db, store.id, original_message, result)
    return result

# Audit checkpoint: keep the takeover guard explicitly documented so future
# changes do not remove the post-generation concurrency check accidentally.
