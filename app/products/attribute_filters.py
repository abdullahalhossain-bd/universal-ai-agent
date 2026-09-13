"""Structured filtering helpers for merchant-defined Product.attributes JSON."""
from __future__ import annotations

import re

from sqlalchemy import Numeric, and_, cast, func, or_


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _number(value):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _text_variants(value: str) -> set[str]:
    text = _norm(value)
    if not text:
        return set()
    variants = {text}
    # Treat common unit spacing as equivalent: 16 GB == 16GB.
    compact = re.sub(
        r"\s+(?=(?:gb|tb|mb|inch|in|cm|mm|kg|g|xl|xxl)\b)",
        "",
        text,
    )
    if compact:
        variants.add(compact)
    return variants


def _json_text(item):
    return func.lower(func.trim(item.as_string()))


def _compact_sql_text(item):
    return func.replace(_json_text(item), " ", "")


def build_attribute_conditions(attributes: dict, attributes_column):
    """Build SQLAlchemy predicates against merchant-defined JSON attributes.

    Keys are supplied by the merchant schema and values are always bound
    parameters. Equality is normalized for case/whitespace and common units;
    numeric operators work for JSON values that are numeric (or numeric text).
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

        item = attributes_column[str(key).strip()]
        number = _number(value)

        if op == "=":
            if isinstance(value, str):
                variants = _text_variants(value)
                if variants:
                    conditions.append(
                        or_(*(_compact_sql_text(item) == re.sub(r"\s+", "", variant) for variant in variants))
                    )
            elif number is not None:
                conditions.append(cast(item.as_string(), Numeric(20, 6)) == number)
            else:
                conditions.append(_json_text(item) == _norm(value))
            continue

        if op == "!=":
            if isinstance(value, str):
                conditions.append(_compact_sql_text(item) != re.sub(r"\s+", "", _norm(value)))
            elif number is not None:
                conditions.append(cast(item.as_string(), Numeric(20, 6)) != number)
            else:
                conditions.append(_json_text(item) != _norm(value))
            continue

        if number is None:
            continue

        # Cast JSON text to a numeric value for comparison operators.
        conditions.append(cast(item.as_string(), Numeric(20, 6)).op(op)(number))

    return conditions


def apply_attribute_filters(query, attributes: dict, attributes_column):
    conditions = build_attribute_conditions(attributes, attributes_column)
    return query.filter(and_(*conditions)) if conditions else query
