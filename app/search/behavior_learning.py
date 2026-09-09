"""Behavioral feedback collection and product ranking signals.

The system learns only from explicit observed events. Missing events never
become invented ratings, sales, popularity, or conversion claims.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import uuid

from app.db.models import BehavioralEvent

EVENT_WEIGHTS = {
    "impression": 0.0,
    "click": 1.0,
    "detail_view": 1.5,
    "add_to_cart": 4.0,
    "purchase": 10.0,
    "favorite": 3.0,
    "dismiss": -1.0,
}

ALLOWED_EVENTS = frozenset(EVENT_WEIGHTS) | {"query_repeat", "query_refine"}


def record_event(
    db,
    *,
    store_id: str,
    interaction_id: str,
    event_type: str,
    product_id: str | None = None,
    conversation_id: str | None = None,
    query: str | None = None,
    value: float | None = None,
    metadata: dict | None = None,
) -> BehavioralEvent:
    if event_type not in ALLOWED_EVENTS:
        raise ValueError(f"Unsupported behavioral event: {event_type}")
    event = BehavioralEvent(
        id=str(uuid.uuid4()),
        interaction_id=interaction_id,
        store_id=store_id,
        product_id=product_id,
        conversation_id=conversation_id,
        event_type=event_type,
        query=(query or "")[:500] or None,
        value=value,
        metadata=metadata or {},
    )
    db.add(event)
    db.commit()
    return event


def get_behavior_scores(db, store_id: str, product_ids: list[str], days: int = 30) -> dict[str, float]:
    """Return decayed behavioral scores for candidate products.

    Scores are store-scoped and based only on recorded customer behavior.
    Recent events have more influence than old events. Impressions carry no
    positive weight, so merely being shown cannot manufacture popularity.
    """
    if not product_ids:
        return {}
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (
        db.query(BehavioralEvent)
        .filter(
            BehavioralEvent.store_id == store_id,
            BehavioralEvent.product_id.in_(product_ids),
            BehavioralEvent.created_at >= cutoff,
        )
        .all()
    )
    scores: dict[str, float] = defaultdict(float)
    now = datetime.utcnow()
    for row in rows:
        weight = EVENT_WEIGHTS.get(row.event_type, 0.0)
        if not weight:
            continue
        age_days = max(0.0, (now - row.created_at).total_seconds() / 86400.0)
        decay = 0.5 ** (age_days / 30.0)
        multiplier = float(row.value) if row.value is not None else 1.0
        scores[str(row.product_id)] += weight * max(0.0, multiplier) * decay
    return dict(scores)


def query_behavior(db, store_id: str, query: str, days: int = 30) -> dict[str, float]:
    """Aggregate behavioral evidence by query family for future learning use."""
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (
        db.query(BehavioralEvent)
        .filter(
            BehavioralEvent.store_id == store_id,
            BehavioralEvent.query == query[:500],
            BehavioralEvent.created_at >= cutoff,
        )
        .all()
    )
    result: dict[str, float] = defaultdict(float)
    for row in rows:
        result[row.event_type] += float(row.value) if row.value is not None else 1.0
    return dict(result)
