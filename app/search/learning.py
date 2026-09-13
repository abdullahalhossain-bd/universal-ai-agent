"""Persistent store-scoped learning for product-search corrections.

This module intentionally keeps learned mappings tenant-scoped. A mapping
learned for one merchant can never be returned for another merchant.
"""
from datetime import datetime
import re
import uuid

from sqlalchemy.exc import IntegrityError

from app.db.models import Product, SearchLearning


PRODUCT_CORRECTION_KIND = "product_correction"
_MAX_QUERY_LENGTH = 255
_MAX_TERM_LENGTH = 255


def normalize_learning_query(value: str) -> str:
    """Return a stable, bounded key for a search-learning lookup."""
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return value[:_MAX_QUERY_LENGTH]


def normalize_learning_term(value: str) -> str:
    """Normalize an LLM/fuzzy correction before persistence."""
    value = re.sub(r"\s+", " ", (value or "").strip())
    value = value.strip(".,!?;:()[]{}\"'")
    return value[:_MAX_TERM_LENGTH]


def get_learned_correction(db, store_id: str, source_query: str) -> str | None:
    """Read only a correction belonging to the requested store."""
    key = normalize_learning_query(source_query)
    if not key:
        return None

    learning = (
        db.query(SearchLearning)
        .filter(
            SearchLearning.store_id == store_id,
            SearchLearning.kind == PRODUCT_CORRECTION_KIND,
            SearchLearning.source_query == key,
        )
        .first()
    )

    if learning is None:
        return None

    learning.hit_count = int(learning.hit_count or 0) + 1
    learning.last_used_at = datetime.utcnow()
    db.commit()
    return learning.corrected_term


def save_learned_correction(
    db,
    store_id: str,
    source_query: str,
    corrected_term: str,
    source: str = "groq",
) -> bool:
    """Persist a successful correction without leaking across stores."""
    key = normalize_learning_query(source_query)
    term = normalize_learning_term(corrected_term)

    if not key or not term or len(term.split()) > 4:
        return False

    existing = (
        db.query(SearchLearning)
        .filter(
            SearchLearning.store_id == store_id,
            SearchLearning.kind == PRODUCT_CORRECTION_KIND,
            SearchLearning.source_query == key,
        )
        .first()
    )

    if existing is not None:
        existing.corrected_term = term
        existing.source = source
        existing.updated_at = datetime.utcnow()
        db.commit()
        return True

    db.add(
        SearchLearning(
            id=str(uuid.uuid4()),
            store_id=store_id,
            kind=PRODUCT_CORRECTION_KIND,
            source_query=key,
            corrected_term=term,
            source=source,
            hit_count=0,
        )
    )

    try:
        db.commit()
        return True
    except IntegrityError:
        # Another request may have learned the same query concurrently.
        db.rollback()
        return False


def correction_matches_store(db, store_id: str, corrected_term: str) -> bool:
    """Only accept a correction that resolves to this store's catalog."""
    term = normalize_learning_term(corrected_term)
    if not term:
        return False

    pattern = f"%{term}%"
    return (
        db.query(Product.id)
        .filter(
            Product.store_id == store_id,
            (
                Product.name.ilike(pattern)
                | Product.description.ilike(pattern)
                | Product.category.ilike(pattern)
            ),
        )
        .first()
        is not None
    )
