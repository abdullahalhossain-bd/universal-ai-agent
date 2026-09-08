"""Confidence scoring for automatic ecommerce datasource mapping."""

from app.connectors.field_hints import FIELD_HINTS

FIELD_NAME_HINTS = FIELD_HINTS


def normalize(text: str) -> str:
    """Normalize snake/camel/kebab/spaced source column names."""
    import re

    value = str(text or "").strip().lower()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _sample_profile(sample_values: list | None):
    values = [v for v in (sample_values or []) if v is not None]
    if not values:
        return {}

    text = [str(v).strip() for v in values if str(v).strip()]
    lower = [v.lower() for v in text]
    numeric = 0
    integer = 0
    urls = 0
    booleans = 0

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
    """Score how likely a source column represents a canonical field."""
    score = 0.0
    normalized_column = normalize(column_name)
    hints = {normalize(h) for h in FIELD_HINTS.get(field, set())}

    if normalized_column in hints:
        score += 0.70
    elif any(h in normalized_column or normalized_column in h for h in hints if h):
        score += 0.35

    profile = _sample_profile(sample_values)
    numeric_types = {"decimal", "float", "numeric", "double", "real", "number"}
    integer_types = {"int", "integer", "bigint", "smallint"}
    text_types = {"text", "varchar", "char", "string"}
    type_name = normalize(column_type or "")

    if field in {"price", "compare_at_price", "discount", "rating", "weight"}:
        if type_name in numeric_types or profile.get("numeric_ratio", 0) >= 0.8:
            score += 0.20
    elif field in {"stock", "review_count"}:
        if type_name in integer_types or profile.get("integer_ratio", 0) >= 0.8:
            score += 0.20
    elif field in {"image", "images", "url"}:
        if profile.get("url_ratio", 0) >= 0.6:
            score += 0.20
    elif field == "availability":
        if profile.get("boolean_ratio", 0) >= 0.6:
            score += 0.20
    elif field in {"id", "sku", "barcode"}:
        if profile.get("unique_ratio", 0) >= 0.8:
            score += 0.10
    elif field in {"name", "description", "brand", "category", "subcategory", "tags", "color", "size", "material", "variant", "currency"}:
        if type_name in text_types:
            score += 0.10

    # A populated sample is useful evidence, but never enough by itself to map a field.
    if profile.get("count", 0):
        score += 0.05

    return round(min(score, 1.0), 4)
