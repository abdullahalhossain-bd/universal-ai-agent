"""Production-grade sync quality analysis helpers."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

from app.sync.mapping_confidence import discover_mapping_with_confidence

URL_SCHEMES = {"http", "https"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "BDT", "INR", "PKR", "AED", "SAR", "CAD", "AUD", "JPY", "CNY", "SGD", "MYR", "NPR"}


def normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def normalize_http_url(value: object) -> str:
    """Normalize a merchant-entered public website URL without weakening SSRF checks."""
    if not isinstance(value, str):
        raise ValueError("website URL must be a string")
    raw = value.strip()
    if not raw:
        raise ValueError("website URL is required")
    if any(ord(ch) < 32 for ch in raw):
        raise ValueError("website URL contains invalid control characters")
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlparse(candidate)
        scheme = parsed.scheme.casefold()
        if scheme not in URL_SCHEMES or not parsed.hostname:
            raise ValueError("website URL must use http or https")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("website URL must not contain username or password")
        # Accessing .port validates malformed/out-of-range ports.
        _ = parsed.port
        if any(ch.isspace() for ch in parsed.netloc):
            raise ValueError("website URL contains invalid whitespace")
    except ValueError as exc:
        if str(exc).startswith("website URL"):
            raise
        raise ValueError("website URL is invalid") from exc
    return candidate


def valid_http_url(value: object) -> bool:
    try:
        normalize_http_url(value)
        return True
    except ValueError:
        return False


def analyze_rows(rows: list[dict]) -> dict:
    """Analyze normalized rows; keep bounded affected-product samples."""
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
        attrs = product.get("attributes") if isinstance(product.get("attributes"), dict) else {}
        sku = product.get("sku") or attrs.get("sku")
        if sku:
            skus[str(sku).strip().casefold()] += 1
        if not str(product.get("name") or "").strip(): add("empty_name", product)
        price = product.get("price")
        if price is not None:
            try:
                if float(price) < 0: add("negative_price", product)
            except (TypeError, ValueError): add("invalid_price", product)
        stock = product.get("stock")
        if stock is not None:
            try:
                if float(stock) < 0: add("invalid_stock", product)
            except (TypeError, ValueError): add("invalid_stock", product)
        currency = product.get("currency")
        if currency and str(currency).upper() not in VALID_CURRENCIES:
            add("invalid_currency", product)
        if not valid_http_url(product.get("product_url")):
            add("invalid_product_url", product)
    for key, count in ids.items():
        if key and count > 1:
            invalid["duplicate_id"].append({"id": key, "count": count})
    for key, count in skus.items():
        if key and count > 1:
            invalid["duplicate_sku"].append({"sku": key, "count": count})
    for key, count in names.items():
        if key and count > 1:
            invalid["duplicate_name"].append({"name": key, "count": count})
    return {"invalid": dict(invalid), "counts": {key: len(value) for key, value in invalid.items()}}
