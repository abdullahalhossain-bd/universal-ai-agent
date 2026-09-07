"""
Normalize a raw merchant row into the local product field shape.

Mapping values may be a column name or the legacy {"column": ...} shape.
Unknown connector columns are intentionally not guessed here; the mapping
engine remains the source of truth for semantic fields.
"""

from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = ("id", "name")


def _resolve_column(mapping: dict, field: str) -> str | None:
    entry = mapping.get(field)
    if entry is None:
        aliases = {"image_url": "image", "product_url": "url"}
        entry = mapping.get(aliases.get(field, ""))
    if isinstance(entry, dict):
        return entry.get("column")
    return entry


def _get(raw: dict, mapping: dict, field: str) -> Any:
    column = _resolve_column(mapping, field)
    return raw.get(column) if column else None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_row(raw: dict, mapping: dict) -> dict | None:
    """Return a Product upsert payload, or None for invalid id/name rows."""
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
        "sku": _as_str(_get(raw, mapping, "sku")),
        "category": _as_str(_get(raw, mapping, "category")),
        "brand": _as_str(_get(raw, mapping, "brand")),
        "image_url": _as_str(_get(raw, mapping, "image_url")),
        "product_url": _as_str(_get(raw, mapping, "product_url")),
    }
