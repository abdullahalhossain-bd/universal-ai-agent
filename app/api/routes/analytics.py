"""Store-scoped merchant analytics derived only from recorded events."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.chat.models import ChatSession
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import BehavioralEvent, Product, QueryEvent, Store
from app.search.behavior_learning import EVENT_WEIGHTS

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])
_SEARCH_INTENTS = ("product_search", "catalog_browse", "mixed")
_QUERY_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "you", "have", "what", "which", "how", "can", "i", "me", "my",
    "please", "show", "give", "for", "of", "to", "in", "on", "with", "and", "or", "this", "that",
    "কি", "কী", "আছে", "আসেন", "দাও", "দেন", "দেখাও", "আমার", "এর", "টা", "টি", "কত", "কোন", "কোনটা",
}


def _since(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


def _event_score(created_at: datetime, event_type: str, value) -> float:
    weight = EVENT_WEIGHTS.get(event_type, 0.0)
    if not weight:
        return 0.0
    now = datetime.utcnow()
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    decay = 0.5 ** (age_days / 30.0)
    multiplier = float(value) if value is not None else 1.0
    return weight * max(0.0, multiplier) * decay


def _question_fingerprint(message: str) -> str:
    """Cluster simple wording variants without an LLM or merchant-specific rules."""
    text = re.sub(r"[^\w\u0980-\u09ff]+", " ", (message or "").casefold())
    tokens = [t for t in text.split() if len(t) > 1 and t not in _QUERY_STOPWORDS]
    return " ".join(sorted(set(tokens))[:12]) or text.strip()[:120]


def _gap_kind(row: QueryEvent) -> tuple[str, str]:
    intent = (row.intent or "").casefold()
    if intent == "manual":
        return "human_handoff", "Agent handed this conversation to a human/team."
    if intent in _SEARCH_INTENTS and not row.had_results:
        return "catalog_gap", "Customers asked for catalog data that produced no matching products."
    if not row.had_results and intent in {"general_question", "product_detail", "link_request"}:
        return "knowledge_gap_candidate", "No structured result was recorded; review this question for missing knowledge/content."
    return "low_signal", "No structured result was recorded."


@router.get("/overview")
def analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    conversations = db.query(func.count(ChatSession.id)).filter(ChatSession.store_id == store.id, ChatSession.created_at >= since).scalar() or 0
    questions = db.query(func.count(QueryEvent.id)).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since).scalar() or 0
    product_searches = db.query(func.count(QueryEvent.id)).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since, QueryEvent.intent.in_(_SEARCH_INTENTS)).scalar() or 0
    unanswered = db.query(func.count(QueryEvent.id)).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since, QueryEvent.had_results.is_(False)).scalar() or 0
    clicks = db.query(func.count(BehavioralEvent.id)).filter(BehavioralEvent.store_id == store.id, BehavioralEvent.created_at >= since, BehavioralEvent.event_type == "click").scalar() or 0
    purchases = db.query(func.count(BehavioralEvent.id)).filter(BehavioralEvent.store_id == store.id, BehavioralEvent.created_at >= since, BehavioralEvent.event_type == "purchase").scalar() or 0
    questions, clicks, purchases = int(questions), int(clicks), int(purchases)
    return {
        "days": days, "conversations": int(conversations), "questions": questions,
        "product_searches": int(product_searches), "unanswered_questions": int(unanswered),
        "unanswered_rate": round(int(unanswered) / questions, 4) if questions else 0.0,
        "answer_coverage_rate": round((questions - int(unanswered)) / questions, 4) if questions else 0.0,
        "clicks": clicks, "purchases": purchases,
        "click_to_purchase_rate": round(purchases / clicks, 4) if clicks else 0.0,
        "conversions": purchases, "conversion_rate": round(purchases / clicks, 4) if clicks else 0.0,
    }


@router.get("/daily")
def analytics_daily(
    days: int = Query(default=30, ge=1, le=365),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    rows = db.query(func.date(QueryEvent.created_at).label("day"), func.count(QueryEvent.id).label("questions"), func.sum(case((QueryEvent.had_results.is_(False), 1), else_=0)).label("unanswered")).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since).group_by(func.date(QueryEvent.created_at)).order_by(func.date(QueryEvent.created_at)).all()
    by_day = {str(row.day): {"questions": int(row.questions or 0), "unanswered": int(row.unanswered or 0)} for row in rows}
    series, cursor, end = [], since.date(), datetime.utcnow().date()
    while cursor <= end:
        key = str(cursor); values = by_day.get(key, {"questions": 0, "unanswered": 0}); series.append({"date": key, **values}); cursor += timedelta(days=1)
    return {"days": days, "series": series}


@router.get("/popular-questions")
def popular_questions(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    rows = db.query(QueryEvent).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= _since(days)).order_by(QueryEvent.created_at.desc()).limit(10000).all()
    groups = {}
    for row in rows:
        key = _question_fingerprint(row.message)
        if key not in groups:
            groups[key] = {"question": row.message, "fingerprint": key, "count": 0, "answered": 0, "unanswered": 0, "intents": Counter(), "examples": []}
        item = groups[key]; item["count"] += 1
        if row.had_results: item["answered"] += 1
        else: item["unanswered"] += 1
        item["intents"][row.intent] += 1
        if len(item["examples"]) < 3 and row.message not in item["examples"]: item["examples"].append(row.message)
    result = sorted(groups.values(), key=lambda x: (-x["count"], -x["unanswered"]))[:limit]
    for item in result:
        item["intents"] = dict(item["intents"])
        item["answer_rate"] = round(item["answered"] / item["count"], 4) if item["count"] else 0.0
    return {"days": days, "questions": result}


@router.get("/knowledge-gaps")
def knowledge_gaps(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    rows = db.query(QueryEvent).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= _since(days), QueryEvent.had_results.is_(False)).order_by(QueryEvent.created_at.desc()).limit(10000).all()
    groups = {}
    for row in rows:
        kind, explanation = _gap_kind(row)
        if kind == "low_signal":
            continue
        key = f"{kind}:{_question_fingerprint(row.message)}"
        if key not in groups:
            groups[key] = {"question": row.message, "kind": kind, "explanation": explanation, "count": 0, "last_seen": row.created_at.isoformat(), "intents": Counter(), "examples": []}
        item = groups[key]; item["count"] += 1; item["intents"][row.intent] += 1
        if row.created_at.isoformat() > item["last_seen"]: item["last_seen"] = row.created_at.isoformat()
        if len(item["examples"]) < 3 and row.message not in item["examples"]: item["examples"].append(row.message)
    result = sorted(groups.values(), key=lambda x: (-x["count"], x["kind"]))[:limit]
    for item in result: item["intents"] = dict(item["intents"])
    return {"days": days, "gaps": result, "note": "These are detected analytics gaps, not a claim that every no-result question was answered incorrectly. Review examples before adding knowledge or catalog data."}


@router.get("/intents")
def analytics_intents(
    days: int = Query(default=30, ge=1, le=365),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    rows = db.query(QueryEvent.intent, func.count(QueryEvent.id).label("count"), func.sum(case((QueryEvent.had_results.is_(False), 1), else_=0)).label("unanswered")).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= _since(days)).group_by(QueryEvent.intent).order_by(func.count(QueryEvent.id).desc()).all()
    return {"days": days, "intents": [{"intent": row.intent, "count": int(row.count or 0), "unanswered": int(row.unanswered or 0)} for row in rows]}


@router.get("/popular-products")
def popular_products(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    rows = db.query(BehavioralEvent).filter(BehavioralEvent.store_id == store.id, BehavioralEvent.created_at >= since, BehavioralEvent.product_id.isnot(None)).all()
    scores: dict[str, float] = {}; counts: dict[str, dict[str, int]] = {}
    for event in rows:
        pid = str(event.product_id); scores[pid] = scores.get(pid, 0.0) + _event_score(event.created_at, event.event_type, event.value); counts.setdefault(pid, {})[event.event_type] = counts.setdefault(pid, {}).get(event.event_type, 0) + 1
    top_ids = [pid for pid in sorted(scores, key=lambda pid: scores[pid], reverse=True) if scores[pid] > 0][:limit]
    if not top_ids: return {"days": days, "products": []}
    products = db.query(Product).filter(Product.store_id == store.id, Product.id.in_(top_ids)).all(); by_id = {str(product.id): product for product in products}; result = []
    for pid in top_ids:
        product = by_id.get(pid)
        if product is None: continue
        events = counts.get(pid, {}); result.append({"product_id": pid, "name": getattr(product, "name", None), "image_url": getattr(product, "image_url", None), "product_url": getattr(product, "product_url", None), "score": round(scores[pid], 2), "impressions": events.get("impression", 0), "clicks": events.get("click", 0), "detail_views": events.get("detail_view", 0), "add_to_cart": events.get("add_to_cart", 0), "purchases": events.get("purchase", 0)})
    return {"days": days, "products": result}


@router.get("/unanswered-questions")
def unanswered_questions(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    rows = db.query(QueryEvent).filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since, QueryEvent.had_results.is_(False)).order_by(QueryEvent.created_at.desc()).limit(limit).all()
    return {"days": days, "questions": [{"message": row.message, "intent": row.intent, "matched_term": row.matched_term, "created_at": row.created_at.isoformat()} for row in rows]}
