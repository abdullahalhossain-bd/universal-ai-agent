"""Per-store catalog vocabulary and merchant-defined attribute schema."""
from __future__ import annotations

import json
import re

from sqlalchemy import distinct, text
from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.db.models import DataSource, Product

_CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_KEY_PREFIX = "store_vocab"
_MIN_TOKEN_LEN = 2
_GENERIC_NAME_NOISE = {
    "the", "and", "for", "with", "new", "pcs", "pack", "set", "combo",
}


class StoreVocabulary(set):
    """Set-compatible vocabulary carrying schema metadata for the planner."""

    def __init__(self, values=(), attribute_schema=None):
        super().__init__(values)
        self.attribute_schema = attribute_schema or {}


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


def _normalize_attribute_schema(mapping: dict | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, definition in ((mapping or {}).get("attributes") or {}).items():
        name = str(key).strip().lower()
        if not name:
            continue
        column = definition.get("column") if isinstance(definition, dict) else definition
        aliases = definition.get("aliases", []) if isinstance(definition, dict) else []
        if isinstance(aliases, str):
            aliases = [aliases]
        candidates = [name, str(column or "").strip()]
        candidates.extend(str(alias).strip() for alias in aliases if str(alias).strip())
        result[name] = list(dict.fromkeys(
            candidate.casefold() for candidate in candidates if candidate
        ))
    return result


def _collect_schema(db: Session, store_id: str) -> dict[str, list[str]]:
    schema: dict[str, list[str]] = {}
    try:
        sources = (
            db.query(DataSource.mapping)
            .filter(
                DataSource.store_id == store_id,
                DataSource.active.is_(True),
            )
            .all()
        )
        for (mapping,) in sources:
            for key, aliases in _normalize_attribute_schema(mapping).items():
                schema[key] = list(dict.fromkeys(schema.get(key, []) + aliases))
    except Exception:
        pass
    return schema


def _collect_from_db(db: Session, store_id: str, schema: dict[str, list[str]]) -> set[str]:
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

    for aliases in schema.values():
        for alias in aliases:
            vocabulary.update(_tokenize(alias))

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
        pass

    return vocabulary


async def get_store_vocabulary(db: Session, store_id: str) -> StoreVocabulary:
    key = _cache_key(store_id)
    try:
        cached = await redis_client.get(key)
        if cached is not None:
            payload = json.loads(cached)
            if isinstance(payload, dict):
                return StoreVocabulary(payload.get("terms", []), payload.get("schema", {}))
            # Backward-compatible cache created by older versions.
            if isinstance(payload, list):
                return StoreVocabulary(payload)
    except Exception:
        pass

    schema = _collect_schema(db, store_id)
    vocabulary = _collect_from_db(db, store_id, schema)
    try:
        await redis_client.set(
            key,
            json.dumps({"terms": sorted(vocabulary), "schema": schema}, ensure_ascii=False),
            ex=_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass
    return StoreVocabulary(vocabulary, schema)


async def invalidate_store_vocabulary(store_id: str) -> None:
    try:
        await redis_client.delete(_cache_key(store_id))
    except Exception:
        pass
