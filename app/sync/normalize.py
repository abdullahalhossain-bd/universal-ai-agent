"""
Normalize a raw merchant row into the local Product field shape.

Mapping keys are semantic types (id, name, price, stock, …). Values may be
either a column name string or a dict with a ``column`` key (legacy shape
from the mapping engine).
"""

from __future__ import annotations

import re
from typing import Any


REQUIRED_FIELDS = ("id", "name")
_CURRENCY_AND_GROUPING = re.compile(r"[^0-9+\-.,]")


def _resolve_column(mapping: dict, field: str) -> str | None:
    entry = mapping.get(field)
    if entry is None:
        aliases = {"image_url": "image", "product_url": "url"}
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
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    # Accept common merchant formats such as "৳1,299", "$ 1,299.50",
    # "1 299.50", while rejecting strings that contain no numeric value.
    text = _CURRENCY_AND_GROUPING.sub("", text).replace(" ", "")
    if not text:
        return None
    # If both separators occur, the last separator is treated as decimal.
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


def normalize_row(raw: dict, mapping: dict) -> dict | None:
    """Return a dict suitable for Product upsert, or None if invalid."""
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
    }
