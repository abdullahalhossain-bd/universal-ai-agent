"""Confidence scoring for automatic ecommerce datasource mapping."""

import re

from app.connectors.field_hints import FIELD_HINTS

# Backward-compatible name. The canonical registry lives in field_hints.py.
FIELD_NAME_HINTS = FIELD_HINTS


def normalize(text: str) -> str:
    """Normalize snake/camel/kebab/spaced source column names."""
    value = str(text or "").strip().lower()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _sample_profile(sample_values: list | None):
    values = [v for v in (sample_values or []) if v is not None]
    if not values:
        return {}

    text = [str(v).strip() for v in values if str(v).strip()]
    if not text:
        return {}

    lower = [v.lower() for v in text]
    numeric = integer = urls = booleans = 0

    for value in text:
        try:
            number = float(value.replace(",", ""))
            numeric += 1
            if number.is_integer():
                integer += 1
        except (TypeError, ValueError):
            pass

        if value.startswith(("http://", "https://", "//")):
            urls += 1
        if value.lower() in {"true", "false", "yes", "no", "0", "1", "in stock", "out of stock"}:
            booleans += 1

    return {
        "count": len(text),
        "numeric_ratio": numeric / len(text),
        "integer_ratio": integer / len(text),
        "url_ratio": urls / len(text),
        "boolean_ratio": booleans / len(text),
        "unique_ratio": len(set(lower)) / len(lower),
    }


def score_column(
    field: str,
    column_name: str,
    column_type: str | None = None,
    sample_values: list | None = None,
) -> float:
    """Score how likely a source column represents a canonical field.

    Name evidence is intentionally strong: an exact canonical field/alias is
    sufficient for automatic mapping. Type/sample evidence is supporting
    evidence and cannot by itself create a mapping.
    """
    normalized_column = normalize(column_name)
    hints = {normalize(h) for h in FIELD_HINTS.get(field, set())}

    if not normalized_column or not hints:
        return 0.0

    # Exact canonical names are the strongest signal. This fixes the old
    # 0.60 + 0.05 scoring problem where obvious fields could never auto-map.
    canonical_name = normalize(field)
    if normalized_column == canonical_name:
        score = 0.95
    elif normalized_column in hints:
        score = 0.90
    elif any(h in normalized_column or normalized_column in h for h in hints if h):
        score = 0.40
    else:
        score = 0.0

    profile = _sample_profile(sample_values)
    numeric_types = {"decimal", "float", "numeric", "double", "real", "number"}
    integer_types = {"int", "integer", "bigint", "smallint"}
    text_types = {"text", "varchar", "char", "string"}
    type_name = normalize(column_type or "")

    if score == 0.0:
        return 0.0

    if field in {"price", "compare_at_price", "discount", "rating", "weight"}:
        if type_name in numeric_types or profile.get("numeric_ratio", 0) >= 0.8:
            score += 0.05
    elif field in {"stock", "review_count"}:
        if type_name in integer_types or profile.get("integer_ratio", 0) >= 0.8:
            score += 0.05
    elif field in {"image", "images", "url"}:
        if profile.get("url_ratio", 0) >= 0.6:
            score += 0.05
    elif field == "availability":
        if profile.get("boolean_ratio", 0) >= 0.6:
            score += 0.05
    elif field in {"id", "sku", "barcode"}:
        if profile.get("unique_ratio", 0) >= 0.8:
            score += 0.03
    elif field in {"name", "description", "brand", "category", "subcategory", "tags", "color", "size", "material", "variant", "currency"}:
        if type_name in text_types:
            score += 0.03

    # Samples only reinforce an already name-supported candidate.
    if profile.get("count", 0):
        score += 0.02

    return round(min(score, 1.0), 4)
