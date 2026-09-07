"""
Normalizers for connector-side field discovery and product mapping.
"""

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    if not name:
        return ""
    lowered = name.lower().strip()
    return _WHITESPACE.sub(" ", lowered)


def _mapped_value(raw: dict, mapping: dict, *fields):
    for field in fields:
        entry = mapping.get(field)
        if isinstance(entry, dict):
            entry = entry.get("column")
        if entry:
            return raw.get(entry)
    return None


def normalize_product(raw: dict, mapping: dict):
    """Normalize all known product fields without dropping connector data."""
    raw_id = _mapped_value(raw, mapping, "id", "external_id")
    name = _mapped_value(raw, mapping, "name")

    return {
        "id": str(raw_id) if raw_id is not None else None,
        "name": name,
        "price": _mapped_value(raw, mapping, "price"),
        "stock": _mapped_value(raw, mapping, "stock", "stock_quantity"),
        "sku": _mapped_value(raw, mapping, "sku"),
        "description": _mapped_value(raw, mapping, "description"),
        "category": _mapped_value(raw, mapping, "category"),
        "brand": _mapped_value(raw, mapping, "brand"),
        "image_url": _mapped_value(raw, mapping, "image_url", "image"),
        "product_url": _mapped_value(raw, mapping, "product_url", "url"),
    }
