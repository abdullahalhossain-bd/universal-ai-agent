"""Structured filtering helpers for merchant-defined Product.attributes JSON."""
from __future__ import annotations

import re
from sqlalchemy import and_, or_


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _number(value):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _text_variants(value: str) -> set[str]:
    text = _norm(value)
    variants = {text}
    # 16 GB == 16GB, 6.5 inch == 6.5in, etc.
    variants.add(re.sub(r"\s+(?=(gb|tb|mb|inch|in|cm|mm|kg|g|xl|xxl)\b)", "", text))
    return {v for v in variants if v}


def build_attribute_conditions(attributes: dict, attributes_column):
    """Build SQLAlchemy predicates against the JSON attributes column.

    Attribute keys are supplied by the merchant schema and values remain
    bound parameters. Unknown keys are ignored rather than turning into SQL.
    Exact text matching is case-insensitive where the DB supports LOWER();
    numeric-looking values additionally match their numeric representation.
    """
    if not attributes:
        return []

    conditions = []
    for key, raw in attributes.items():
        if raw is None or not str(key).strip():
            continue
        op = "="
        value = raw
        if isinstance(raw, dict):
            value = raw.get("value")
            op = str(raw.get("op", "=")).strip()
        if value is None or op not in {"=", "!=", ">", ">=", "<", "<="}:
            continue

        item = attributes_column[key]
        number = _number(value)
        if op == "=" and number is not None:
            # Merchant sync commonly stores "16GB" as text, so equality
            # needs both normalized text and numeric fallback.
            variants = _text_variants(value)
            text_clauses = [item.as_string().ilike(v) for v in variants]
            conditions.append(or_(*text_clauses))
        elif op == "=" and isinstance(value, str):
            conditions.append(item.as_string().ilike(_norm(value)))
        elif op == "!=":
            conditions.append(item.as_string().not_ilike(_norm(value)))
        else:
            if number is None:
                continue
            try:
                conditions.append(item.as_numeric() .op(op)(number))
            except Exception:
                conditions.append(item.as_string().op(op)(str(value)))
    return conditions


def apply_attribute_filters(query, attributes: dict, attributes_column):
    conditions = build_attribute_conditions(attributes, attributes_column)
    return query.filter(and_(*conditions)) if conditions else query
