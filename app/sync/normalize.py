"""Normalize a raw merchant row into the local Product field shape.

Merchant-specific fields live under the ``attributes`` namespace. Mapping
entries may be strings or ``{"column": ..., "aliases": [...]}`` objects.
"""
from __future__ import annotations

import re
from typing import Any

REQUIRED_FIELDS = ("id", "name")
_CURRENCY_AND_GROUPING = re.compile(r"[^0-9+\-.,]")


def _resolve_column(mapping: dict, field: str) -> str | None:
    entry = mapping.get(field)
    if entry is None:
        entry = mapping.get({"image_url": "image", "product_url": "url"}.get(field, ""))
    if isinstance(entry, dict):
        return entry.get("column")
    return entry


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
        "image_url": _as_str(_get(raw, mapping, "image_url")),
        "product_url": _as_str(_get(raw, mapping, "product_url")),
        "attributes": _extract_attributes(raw, mapping),
    }
