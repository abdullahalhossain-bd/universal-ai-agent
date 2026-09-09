"""Merchant-schema-driven semantic attribute extraction.

The merchant defines the attribute schema; the language model only maps the
customer's natural language to those declared keys. No global RAM/color/fabric
vocabulary is required. Deterministic extraction runs first; the LLM is a
cached fallback for paraphrases and mixed Bangla/Banglish/English phrasing.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from app.core.redis import redis_client


def _norm(value: str) -> str:
    value = str(value or "").casefold().strip()
    value = re.sub(r"[^\w\u0980-\u09ff.+#%\"']+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _definition_parts(definition: Any) -> tuple[str, list[str]]:
    if isinstance(definition, dict):
        name = str(definition.get("column") or "").strip()
        aliases = definition.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        return name, [str(a).strip() for a in aliases if str(a).strip()]
    return str(definition or "").strip(), []


def normalize_schema(mapping: dict | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, definition in ((mapping or {}).get("attributes") or {}).items():
        key = str(key).strip().lower()
        if not key:
            continue
        column, aliases = _definition_parts(definition)
        candidates = [key]
        if column:
            candidates.append(column)
        candidates.extend(aliases)
        result[key] = list(dict.fromkeys(_norm(x) for x in candidates if _norm(x)))
    return result


def deterministic_extract(query: str, schema: dict[str, list[str]]) -> dict[str, Any]:
    """Extract obvious key/value phrases without a fixed global attribute list."""
    text = _norm(query)
    result: dict[str, Any] = {}
    for key, aliases in schema.items():
        for alias in aliases:
            escaped = re.escape(alias)
            patterns = [
                rf"(?:^|\s){escaped}\s*(?:is|=|:|of|er|এর|হলো|হয়|হয়)?\s*([\w\u0980-\u09ff.+#%\"'-]+(?:\s+(?:gb|tb|kg|g|cm|mm|inch|in|ft|year|years|বছর))?)",
                rf"([\w\u0980-\u09ff.+#%\"'-]+(?:\s+(?:gb|tb|kg|g|cm|mm|inch|in|ft|year|years|বছর))?)\s+{escaped}(?:\s|$)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group(1).strip(" ,.;:!?\"")
                    if value and value.casefold() not in {a.casefold() for a in aliases}:
                        result[key] = value
                        break
            if key in result:
                break
    return result


def _cache_key(query: str, schema: dict[str, list[str]]) -> str:
    schema_text = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    # Stable enough for Redis and avoids storing raw merchant data in the key.
    import hashlib
    digest = hashlib.sha256(schema_text.encode()).hexdigest()[:16]
    qdigest = hashlib.sha256(_norm(query).encode()).hexdigest()[:32]
    return f"semantic_attr:{digest}:{qdigest}"


async def extract_semantic_attributes(
    query: str,
    schema: dict[str, list[str]],
    llm_generate: Callable[[list[dict]], Awaitable[dict]] | None = None,
) -> dict[str, Any]:
    if not query or not schema:
        return {}

    deterministic = deterministic_extract(query, schema)
    if deterministic:
        return deterministic

    if llm_generate is None:
        return {}

    key = _cache_key(query, schema)
    try:
        cached = await redis_client.get(key)
        if cached:
            value = json.loads(cached)
            return value if isinstance(value, dict) else {}
    except Exception:
        pass

    schema_for_prompt = {
        key: aliases for key, aliases in schema.items()
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an ecommerce query parser. Map ONLY customer-requested "
                "product attributes to the merchant-declared schema below. "
                "Understand Bangla, Banglish and English, including paraphrases. "
                "Do not invent keys or values. Preserve values exactly enough for "
                "catalog matching (for example 16GB, XL, black, 5kg, 2 years). "
                "Return ONLY valid JSON object: {\"attribute_key\": \"value\"}. "
                "Return {} when no declared attribute is requested.\n\n"
                + json.dumps(schema_for_prompt, ensure_ascii=False)
            ),
        },
        {"role": "user", "content": query},
    ]

    try:
        response = await llm_generate(messages)
        raw = str((response or {}).get("text") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        parsed = json.loads(raw)
    except Exception:
        return {}

    if not isinstance(parsed, dict):
        return {}

    allowed = set(schema)
    result = {
        str(key).strip().lower(): value
        for key, value in parsed.items()
        if str(key).strip().lower() in allowed
        and isinstance(value, (str, int, float, bool))
        and str(value).strip()
    }

    try:
        await redis_client.set(key, json.dumps(result, ensure_ascii=False), ex=24 * 60 * 60)
    except Exception:
        pass
    return result
