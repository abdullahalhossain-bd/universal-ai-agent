"""Deterministic, merchant-data-driven recommendation ranking.

"Best" is not treated as a fixed sort. The ranker first respects all
structured filters, then adapts the score to signals present in the customer's
query and the merchant's actual product data. No global product taxonomy is
required.
"""
from __future__ import annotations

import re
from typing import Iterable

_BEST_CUES = {
    "best", "top", "recommend", "recommended", "suggest", "suggestion",
    "ভালো", "সেরা", "ভাল", "সর্বোত্তম", "সাজেস্ট", "রিকমেন্ড",
}
_PERFORMANCE_CUES = {"performance", "powerful", "fast", "speed", "পারফরম্যান্স", "শক্তিশালী", "দ্রুত"}
_VALUE_CUES = {"value", "worth", "budget", "affordable", "দাম", "বাজেট", "সাশ্রয়ী", "সাশ্রয়ী"}
_PREMIUM_CUES = {"premium", "flagship", "luxury", "প্রিমিয়াম", "প্রিমিয়াম"}
_POPULAR_CUES = {"popular", "bestseller", "best-seller", "বেস্টসেলার", "জনপ্রিয়", "জনপ্রিয়"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\w\u0980-\u09ff.+#%-]+", text.casefold()) if len(t) > 1]


def is_recommendation_query(query: str) -> bool:
    tokens = set(_tokens(query))
    return bool(tokens & _BEST_CUES or any(x in query.casefold() for x in ("best seller", "best-seller", "সবচেয়ে ভালো", "সবচেয়ে ভালো")))


def _attribute_text(product) -> str:
    attrs = getattr(product, "attributes", None) or {}
    parts = []
    if isinstance(attrs, dict):
        for key, value in attrs.items():
            parts.extend([str(key), str(value)])
    return " ".join(parts).casefold()


def _numeric_values(product) -> list[float]:
    values = []
    attrs = getattr(product, "attributes", None) or {}
    if not isinstance(attrs, dict):
        return values
    for value in attrs.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
        else:
            match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)", str(value))
            if match:
                values.append(float(match.group(1)))
    return values


def rank_products(products: Iterable, query: str) -> list:
    """Rank already-filtered products for a recommendation request.

    Signals are intentionally weak and composable: query relevance is the
    strongest signal, followed by explicit merchant popularity/performance/
    premium/value hints when their data exists. With no explicit criterion,
    the default is a balanced best-value score rather than simply cheapest.
    """
    items = list(products)
    if len(items) <= 1:
        return items

    q = query.casefold()
    qtokens = set(_tokens(q)) - _BEST_CUES
    performance = bool(qtokens & _PERFORMANCE_CUES)
    value = bool(qtokens & _VALUE_CUES)
    premium = bool(qtokens & _PREMIUM_CUES)
    popular = bool(qtokens & _POPULAR_CUES)

    prices = [float(p.price) for p in items if getattr(p, "price", None) is not None]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None

    def price_value(product) -> float:
        if min_price is None or max_price is None or max_price == min_price or product.price is None:
            return 0.5
        return (max_price - float(product.price)) / (max_price - min_price)

    def score(product) -> float:
        name = str(getattr(product, "name", "") or "").casefold()
        category = str(getattr(product, "category", "") or "").casefold()
        description = str(getattr(product, "description", "") or "").casefold()
        attrs = _attribute_text(product)
        searchable = f"{name} {category} {description} {attrs}"

        relevance = sum(1 for token in qtokens if token in searchable) / max(1, len(qtokens))
        stock = getattr(product, "stock", None)
        stock_signal = 1.0 if stock is not None and float(stock) > 0 else 0.0
        completeness = min(1.0, len((getattr(product, "attributes", None) or {})) / 5.0)

        # Merchant-defined popularity/performance can be represented by
        # attribute names/values such as "bestseller", "performance",
        # "rating", "featured" without requiring those keys globally.
        popularity_signal = 1.0 if any(cue in attrs for cue in _POPULAR_CUES) else 0.0
        performance_signal = 1.0 if any(cue in attrs or cue in searchable for cue in _PERFORMANCE_CUES) else 0.0
        premium_signal = 1.0 if any(cue in attrs or cue in searchable for cue in _PREMIUM_CUES) else 0.0

        if popular:
            return relevance * 0.45 + popularity_signal * 0.40 + stock_signal * 0.15
        if premium:
            return relevance * 0.45 + premium_signal * 0.40 + price_value(product) * 0.15
        if performance:
            numeric = _numeric_values(product)
            performance_numeric = min(1.0, (max(numeric) / 1000.0)) if numeric else 0.0
            return relevance * 0.55 + performance_signal * 0.30 + performance_numeric * 0.15
        if value:
            return relevance * 0.55 + price_value(product) * 0.30 + completeness * 0.15

        # Ambiguous "best": balanced relevance + value + catalog richness.
        return relevance * 0.55 + price_value(product) * 0.25 + completeness * 0.10 + stock_signal * 0.10

    return sorted(items, key=lambda p: (-score(p), str(getattr(p, "name", "")).casefold()))
