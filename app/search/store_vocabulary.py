"""
Per-store product vocabulary, collected automatically from each
merchant's own catalog (distinct categories + significant words from
product names) instead of relying only on the fixed global word list.

Why this exists:
`app.planner.rule_planner.PRODUCT_WORDS` is a fixed, hand-maintained
list (laptop, phone, shoe, জুতা, মোবাইল, ...). It only recognizes
product-search intent for words someone thought to add ahead of time.
This is a multi-tenant SaaS, though — one store sells electronics,
another sells sarees, another sells groceries. A merchant selling
"মশারি" (mosquito net) or "কার্পেট" (carpet) gets zero product_score
for those words, so a customer message like "কার্পেট আছে?" falls
through to intent=UNKNOWN and gets the generic "hello, how can I
help?" reply — even though the product exists in that merchant's own
database.

`get_store_vocabulary()` fixes that by reading the store's actual
`products` table (categories + tokenized product-name words) and
handing that back as a per-store term set the planner can add to its
static PRODUCT_WORDS when scoring intent. Cached in Redis with a
short TTL so it doesn't hit the DB on every chat message; call
`invalidate_store_vocabulary()` after a sync/import so new
categories are picked up immediately instead of waiting for the TTL.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.db.models import Product

# Catalogs don't change minute to minute, so a few hours of staleness
# is fine — invalidate_store_vocabulary() covers the "just synced new
# products" case without waiting this out.
_CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_KEY_PREFIX = "store_vocab"

# Tokens too short or too generic to usefully signal "this message is
# about a product" on their own (unlike app.planner.rule_planner's
# STOP_WORDS, which filters *message* text, this filters raw catalog
# text — different noise profile: SKUs, packaging words, filler).
_MIN_TOKEN_LEN = 3
_GENERIC_NAME_NOISE = {
    "the", "and", "for", "with", "new", "pcs", "pack", "set",
    "combo", "item", "items", "size", "color", "colour", "model",
}


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()

    tokens = re.split(r"[\s,/\-_()\[\]।]+", text.lower())

    return {
        token
        for token in tokens
        if len(token) >= _MIN_TOKEN_LEN
        and token not in _GENERIC_NAME_NOISE
        and not token.isdigit()
    }


def _cache_key(store_id: str) -> str:
    return f"{_CACHE_KEY_PREFIX}:{store_id}"


def _collect_from_db(db: Session, store_id: str) -> set[str]:
    vocabulary: set[str] = set()

    categories = (
        db.query(distinct(Product.category))
        .filter(
            Product.store_id == store_id,
            Product.category.isnot(None),
        )
        .all()
    )

    for (category,) in categories:
        vocabulary.update(_tokenize(category))

    names = (
        db.query(Product.name)
        .filter(Product.store_id == store_id)
        .all()
    )

    for (name,) in names:
        vocabulary.update(_tokenize(name))

    return vocabulary


async def get_store_vocabulary(
    db: Session,
    store_id: str,
) -> set[str]:
    """
    Return the set of product-related words for this store: every
    distinct category plus significant words pulled from product
    names. Cached in Redis; a Redis miss or outage just means a
    fresh DB read, never a broken chat response.
    """
    key = _cache_key(store_id)

    try:
        cached = await redis_client.get(key)
        if cached is not None:
            return set(json.loads(cached))
    except Exception:
        pass

    vocabulary = _collect_from_db(db, store_id)

    try:
        await redis_client.set(
            key,
            json.dumps(sorted(vocabulary)),
            ex=_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass

    return vocabulary


async def invalidate_store_vocabulary(store_id: str) -> None:
    """
    Call after a product sync/import completes so the very next chat
    message reflects newly added categories/products, rather than
    waiting up to _CACHE_TTL_SECONDS for the cache to expire on its
    own.
    """
    try:
        await redis_client.delete(_cache_key(store_id))
    except Exception:
        pass
