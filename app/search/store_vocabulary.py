"""Per-store catalog vocabulary, including merchant-defined attributes.

This is a fallback/search-optimization layer, not the source of semantic
understanding. Attribute keys and observed values are harvested from each
merchant's own catalog so new fields such as RAM, fabric, warranty or width
do not require platform code changes.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import distinct, text
from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.db.models import Product

_CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_KEY_PREFIX = "store_vocab"
_MIN_TOKEN_LEN = 2
_GENERIC_NAME_NOISE = {
    "the", "and", "for", "with", "new", "pcs", "pack", "set", "combo",
    "item", "items", "size", "color", "colour", "model",
}


def _tokenize(text_value: str | None) -> set[str]:
    if not text_value:
        return set()
    tokens = re.split(r"[\s,/\-_()\[\]।:]+", str(text_value).casefold())
    return {
        token for token in tokens
        if len(token) >= _MIN_TOKEN_LEN
        and token not in _GENERIC_NAME_NOISE
    }


def _cache_key(store_id: str) -> str:
    return f"{_CACHE_KEY_PREFIX}:{store_id}"


def _collect_from_db(db: Session, store_id: str) -> set[str]:
    vocabulary: set[str] = set()

    categories = (
        db.query(distinct(Product.category))
        .filter(Product.store_id == store_id, Product.category.isnot(None))
        .all()
    )
    for (category,) in categories:
        vocabulary.update(_tokenize(category))

    names = db.query(Product.name).filter(Product.store_id == store_id).all()
    for (name,) in names:
        vocabulary.update(_tokenize(name))

    # Dynamic attributes are stored as JSON. Read them with a raw SELECT so
    # this vocabulary layer remains compatible with databases/migrations
    # where the ORM model is being rolled out independently.
    try:
        rows = db.execute(
            text("SELECT attributes FROM products WHERE store_id = :store_id"),
            {"store_id": store_id},
        ).scalars().all()
        for raw in rows:
            if not raw:
                continue
            try:
                attrs = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(attrs, dict):
                continue
            for key, value in attrs.items():
                vocabulary.update(_tokenize(str(key)))
                if isinstance(value, (str, int, float, bool)):
                    vocabulary.update(_tokenize(str(value)))
    except Exception:
        # Older databases without the migration still get normal catalog
        # vocabulary; dynamic attributes simply remain unavailable.
        pass

    return vocabulary


async def get_store_vocabulary(db: Session, store_id: str) -> set[str]:
    key = _cache_key(store_id)
    try:
        cached = await redis_client.get(key)
        if cached is not None:
            return set(json.loads(cached))
    except Exception:
        pass

    vocabulary = _collect_from_db(db, store_id)
    try:
        await redis_client.set(key, json.dumps(sorted(vocabulary), ensure_ascii=False), ex=_CACHE_TTL_SECONDS)
    except Exception:
        pass
    return vocabulary


async def invalidate_store_vocabulary(store_id: str) -> None:
    try:
        await redis_client.delete(_cache_key(store_id))
    except Exception:
        pass
