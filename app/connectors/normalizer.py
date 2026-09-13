"""
Normalizers for connector-side field discovery and product mapping.
"""

import re

# Strip leading/trailing whitespace and collapse internal whitespace.
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """
    Lowercase and collapse whitespace, but preserve separators like `_` and `-`
    so the result can be matched against hint sets that include tokens such as
    `item_ref` or `available_qty`.

    Used by `MappingEngine.suggest` to compare column names against field
    hint sets such as `{"product_id", "item_ref", "id"}`.

    Examples:
        - "Item Ref"      -> "item ref"
        - "  item_title " -> "item_title"
        - "SELL_AMT"      -> "sell_amt"
        - "available qty" -> "available qty"
    """

    if not name:
        return ""

    lowered = name.lower().strip()

    # Collapse internal whitespace but keep separators (_ and -) intact
    # so hint matching still works for tokens like "item_ref".
    return _WHITESPACE.sub(" ", lowered)


def normalize_product(raw: dict, mapping: dict):
    """
    Build a normalized product dict from a raw row using a field -> column
    mapping (the mapping values can be either strings or dicts containing
    a "column" key, for backward compatibility with the older connector
    mapping shape).
    """

    def get_mapped(field):
        entry = mapping.get(field)

        if isinstance(entry, dict):
            column = entry.get("column")
        else:
            column = entry

        if column is None:
            return None

        return raw.get(column)

    return {
        "id": str(get_mapped("id")),
        "name": get_mapped("name"),
        "price": get_mapped("price"),
        "stock": get_mapped("stock"),
        "image_url": get_mapped("image_url"),
    }
