"""
Normalize a raw merchant row into the local Product field shape.

Mapping keys are semantic types (id, name, price, stock, …). Values may be
either a column name string or a dict with a ``column`` key (legacy shape
from the mapping engine).

Only fields that exist on the products table are produced:
  id, name, description, price, stock, image_url, product_url
"""

from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = ("id", "name")


def _resolve_column(mapping: dict, field: str) -> str | None:
    entry = mapping.get(field)
    if entry is None:
        # Alias: mapping engines use "image" / "url" while the ORM uses
        # image_url / product_url.
        aliases = {
            "image_url": "image",
            "product_url": "url",
        }
        alt = aliases.get(field)
        if alt:
            entry = mapping.get(alt)
    if isinstance(entry, dict):
        return entry.get("column")
    return entry


def _get(raw: dict, mapping: dict, field: str) -> Any:
    column = _resolve_column(mapping, field)
    if not column:
        return None
    return raw.get(column)


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
    """
    Return a dict suitable for Product upsert, or None if the row cannot
    be normalized (missing required id/name).
    """
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
        "image_url": _as_str(_get(raw, mapping, "image_url")),
        "product_url": _as_str(_get(raw, mapping, "product_url")),
    }
