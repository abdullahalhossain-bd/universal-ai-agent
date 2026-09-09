"""Merchant-facing analytics.

This is the store-scoped counterpart to /v1/admin/analytics/* (which
requires PlatformAdmin auth and therefore cannot be called from the
merchant dashboard). Every number here is derived from data already
being recorded elsewhere:

  - ChatSession                -> total conversations
  - QueryEvent                -> questions, product searches,
                                   unanswered questions (had_results=False)
  - BehavioralEvent            -> clicks, conversions, popular products
                                   (see app/search/behavior_learning.py
                                   for the event_type -> weight mapping)

Nothing here invents a number the underlying tables don't actually
have a row for.
"""
from __future__ import annotations

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


def _since(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


@router.get("/overview")
def analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)

    conversations = (
        db.query(func.count(ChatSession.id))
        .filter(ChatSession.store_id == store.id, ChatSession.created_at >= since)
        .scalar() or 0
    )

    questions = (
        db.query(func.count(QueryEvent.id))
        .filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since)
        .scalar() or 0
    )

    product_searches = (
        db.query(func.count(QueryEvent.id))
        .filter(
            QueryEvent.store_id == store.id,
            QueryEvent.created_at >= since,
            QueryEvent.intent.in_(_SEARCH_INTENTS),
        )
        .scalar() or 0
    )

    unanswered = (
        db.query(func.count(QueryEvent.id))
        .filter(
            QueryEvent.store_id == store.id,
            QueryEvent.created_at >= since,
            QueryEvent.had_results.is_(False),
        )
        .scalar() or 0
    )

    clicks = (
        db.query(func.count(BehavioralEvent.id))
        .filter(
            BehavioralEvent.store_id == store.id,
            BehavioralEvent.created_at >= since,
            BehavioralEvent.event_type == "click",
        )
        .scalar() or 0
    )

    conversions = (
        db.query(func.count(BehavioralEvent.id))
        .filter(
            BehavioralEvent.store_id == store.id,
            BehavioralEvent.created_at >= since,
            BehavioralEvent.event_type == "purchase",
        )
        .scalar() or 0
    )

    questions = int(questions)
    clicks = int(clicks)

    return {
        "days": days,
        "conversations": int(conversations),
        "questions": questions,
        "product_searches": int(product_searches),
        "unanswered_questions": int(unanswered),
        "unanswered_rate": round(unanswered / questions, 4) if questions else 0.0,
        "clicks": clicks,
        "conversions": int(conversions),
        "conversion_rate": round(conversions / clicks, 4) if clicks else 0.0,
    }


@router.get("/daily")
def analytics_daily(
    days: int = Query(default=30, ge=1, le=365),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    rows = (
        db.query(
            func.date(QueryEvent.created_at).label("day"),
            func.count(QueryEvent.id).label("questions"),
            func.sum(case((QueryEvent.had_results.is_(False), 1), else_=0)).label("unanswered"),
        )
        .filter(QueryEvent.store_id == store.id, QueryEvent.created_at >= since)
        .group_by(func.date(QueryEvent.created_at))
        .order_by(func.date(QueryEvent.created_at))
        .all()
    )
    return {
        "days": days,
        "series": [
            {"date": str(r.day), "questions": int(r.questions), "unanswered": int(r.unanswered or 0)}
            for r in rows
        ],
    }


@router.get("/popular-products")
def popular_products(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)

    rows = (
        db.query(
            BehavioralEvent.product_id,
            BehavioralEvent.event_type,
            func.count(BehavioralEvent.id),
        )
        .filter(
            BehavioralEvent.store_id == store.id,
            BehavioralEvent.created_at >= since,
            BehavioralEvent.product_id.isnot(None),
        )
        .group_by(BehavioralEvent.product_id, BehavioralEvent.event_type)
        .all()
    )

    scores: dict[str, float] = {}
    counts: dict[str, dict[str, int]] = {}
    for product_id, event_type, count in rows:
        weight = EVENT_WEIGHTS.get(event_type, 0.0)
        scores[product_id] = scores.get(product_id, 0.0) + weight * int(count)
        counts.setdefault(product_id, {})[event_type] = int(count)

    top_ids = sorted(scores, key=lambda pid: scores[pid], reverse=True)[:limit]
    if not top_ids:
        return {"days": days, "products": []}

    products = (
        db.query(Product)
        .filter(Product.store_id == store.id, Product.id.in_(top_ids))
        .all()
    )
    by_id = {p.id: p for p in products}

    result = []
    for pid in top_ids:
        product = by_id.get(pid)
        events = counts.get(pid, {})
        result.append({
            "product_id": pid,
            "name": getattr(product, "name", None),
            "image_url": getattr(product, "image_url", None),
            "score": round(scores[pid], 2),
            "impressions": events.get("impression", 0),
            "clicks": events.get("click", 0),
            "detail_views": events.get("detail_view", 0),
            "add_to_cart": events.get("add_to_cart", 0),
            "purchases": events.get("purchase", 0),
        })

    return {"days": days, "products": result}


@router.get("/unanswered-questions")
def unanswered_questions(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    since = _since(days)
    rows = (
        db.query(QueryEvent)
        .filter(
            QueryEvent.store_id == store.id,
            QueryEvent.created_at >= since,
            QueryEvent.had_results.is_(False),
        )
        .order_by(QueryEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "days": days,
        "questions": [
            {
                "message": r.message,
                "intent": r.intent,
                "matched_term": r.matched_term,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
