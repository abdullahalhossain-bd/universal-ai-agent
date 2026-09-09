"""Normalize a raw merchant row into the local Product field shape.

Merchant-specific fields live under the ``attributes`` namespace. Mapping
entries may be strings or ``{"column": ..., "aliases": [...]}`` objects.
"""
from __future__ import annotations

import json
import re
from typing import Any

REQUIRED_FIELDS = ("id", "name")
_CURRENCY_AND_GROUPING = re.compile(r"[^0-9+\-.,]")


def _resolve_column(mapping: dict, field: str) -> str | None:
    # Prefer explicit canonical fields, then support common singular/plural
    # aliases produced by automatic datasource mapping.
    aliases = {
        "image_url": ("image_url", "image", "images"),
        "product_url": ("product_url", "url"),
    }

    for key in aliases.get(field, (field,)):
        entry = mapping.get(key)
        if entry is None:
            continue
        if isinstance(entry, dict):
            column = entry.get("column")
        else:
            column = entry
        if isinstance(column, str) and column.strip():
            return column
    return None


def _get(raw: dict, mapping: dict, field: str) -> Any:
    column = _resolve_column(mapping, field)
    return raw.get(column) if column else None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = _CURRENCY_AND_GROUPING.sub("", text).replace(" ", "")
    if not text:
        return None
    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1 and len(text.rsplit(",", 1)[1]) != 3:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_image_url(value: Any) -> str | None:
    """Extract the first image URL from scalar, list, dict, or JSON gallery data."""
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first_image_url(item)
            if found:
                return found
        return None

    if isinstance(value, dict):
        for key in ("url", "src", "image_url", "image", "thumbnail"):
            if key in value:
                found = _first_image_url(value[key])
                if found:
                    return found
        return None

    text = _as_str(value)
    if not text:
        return None

    # Some merchant databases store a gallery as JSON text in one column.
    if text[:1] in "[{":
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if parsed is not None:
            found = _first_image_url(parsed)
            if found:
                return found

    return text


def _normalize_attribute_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool, list, dict)):
        return value
    return str(value).strip() or None


def _extract_attributes(raw: dict, mapping: dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    attribute_mapping = mapping.get("attributes") or {}
    if not isinstance(attribute_mapping, dict):
        return result
    for semantic_name, entry in attribute_mapping.items():
        key = str(semantic_name).strip().lower()
        column = entry.get("column") if isinstance(entry, dict) else entry
        if not key or not isinstance(column, str) or not column.strip():
            continue
        value = _normalize_attribute_value(raw.get(column))
        if value is not None:
            result[key] = value
    return result


def normalize_row(raw: dict, mapping: dict) -> dict | None:
    raw_id = _get(raw, mapping, "id")
    raw_name = _get(raw, mapping, "name")
    if raw_id is None or raw_name is None:
        return None

    product_id = str(raw_id).strip()
    name = str(raw_name).strip()
    if not product_id or not name:
        return None

    return {
        "id": product_id,
        "name": name,
        "description": _as_str(_get(raw, mapping, "description")),
        "price": _as_float(_get(raw, mapping, "price")),
        "stock": _as_float(_get(raw, mapping, "stock")),
        "category": _as_str(_get(raw, mapping, "category")),
        "image_url": _first_image_url(_get(raw, mapping, "image_url")),
        "product_url": _as_str(_get(raw, mapping, "product_url")),
        "attributes": _extract_attributes(raw, mapping),
    }
