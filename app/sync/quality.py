"""Production-grade sync quality analysis helpers."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

from app.sync.normalize import discover_mapping_with_confidence

URL_SCHEMES = {"http", "https"}
VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "BDT", "INR", "PKR", "AED", "SAR", "CAD", "AUD", "JPY", "CNY", "SGD", "MYR", "NPR"
}


def normalize_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return text


def valid_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme.casefold() in URL_SCHEMES and bool(parsed.netloc)
    except ValueError:
        return False


def analyze_rows(rows: list[dict]) -> dict:
    """Analyze a normalized source snapshot without changing the DB."""
    invalid: dict[str, list[dict]] = defaultdict(list)
    ids: Counter[str] = Counter()
    skus: Counter[str] = Counter()
    names: Counter[str] = Counter()

    def add(kind: str, product: dict):
        if len(invalid[kind]) < 100:
            invalid[kind].append({"id": str(product.get("id")), "name": product.get("name")})

    for product in rows:
        pid = str(product.get("id") or "").strip()
        ids[pid] += 1
        name = normalize_name(product.get("name"))
        if name:
            names[name] += 1
        sku = product.get("sku") or product.get("attributes", {}).get("sku") if isinstance(product.get("attributes"), dict) else None
        if sku:
            skus[str(sku).strip().casefold()] += 1
        if not str(product.get("name") or "").strip():
            add("empty_name", product)
        price = product.get("price")
        if price is not None:
            try:
                if float(price) < 0:
                    add("negative_price", product)
            except (TypeError, ValueError):
                add("invalid_price", product)
        stock = product.get("stock")
        if stock is not None:
            try:
                if float(stock) < 0:
                    add("invalid_stock", product)
            except (TypeError, ValueError):
                add("invalid_stock", product)
        currency = product.get("currency")
        if currency and str(currency).upper() not in VALID_CURRENCIES:
            add("invalid_currency", product)
        url = product.get("product_url")
        if url and not valid_http_url(url):
            add("malformed_url", product)
        image = product.get("image_url")
        if image and not valid_http_url(image):
            add("invalid_image_url", product)

    duplicate_ids = {k: v for k, v in ids.items() if k and v > 1}
    duplicate_skus = {k: v for k, v in skus.items() if v > 1}
    duplicate_names = {k: v for k, v in names.items() if v > 1}
    duplicates = {
        "duplicate_id_count": sum(v - 1 for v in duplicate_ids.values()),
        "duplicate_sku_count": sum(v - 1 for v in duplicate_skus.values()),
        "possible_duplicate_name_count": sum(v - 1 for v in duplicate_names.values()),
        "sample_ids": list(duplicate_ids)[:20],
        "sample_skus": list(duplicate_skus)[:20],
        "sample_names": list(duplicate_names)[:20],
    }
    return {"invalid": dict(invalid), "duplicates": duplicates}


def schema_analysis(raw: dict, previous_mapping: dict | None = None) -> dict:
    current = discover_mapping_with_confidence(raw, previous_mapping or {})
    previous = previous_mapping or {}
    previous_fields = {k: v for k, v in previous.items() if not k.startswith("_")}
    changes = []
    for field, candidate in current.items():
        if not candidate:
            continue
        old = previous_fields.get(field)
        old = old.get("column") if isinstance(old, dict) else old
        if old and old != candidate["column"]:
            changes.append({"field": field, "previous": old, "current": candidate["column"], "confidence_pct": candidate["confidence_pct"]})
    return {"current": current, "changes": changes, "changed": bool(changes)}


def repair_suggestions(schema: dict, quality: dict) -> list[dict]:
    suggestions = []
    current = schema.get("current", {})
    for field, candidate in current.items():
        if not candidate or candidate.get("confidence_pct", 0) < 85:
            continue
        missing = quality.get("fields", {}).get(field, {}).get("missing", 0)
        if missing:
            suggestions.append({
                "field": field,
                "column": candidate["column"],
                "confidence_pct": candidate["confidence_pct"],
                "missing": missing,
                "action": "apply_mapping",
            })
    return suggestions
