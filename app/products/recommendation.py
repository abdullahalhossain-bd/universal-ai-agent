"""Deterministic, merchant-data-driven recommendation ranking."""
from __future__ import annotations
import re
from typing import Iterable

_BEST_CUES = {"best", "top", "recommend", "recommended", "suggest", "suggestion", "ভালো", "সেরা", "ভাল", "সর্বোত্তম", "সাজেস্ট", "রিকমেন্ড"}
_PERFORMANCE_CUES = {"performance", "powerful", "fast", "speed", "পারফরম্যান্স", "শক্তিশালী", "দ্রুত"}
_VALUE_CUES = {"value", "worth", "budget", "affordable", "দাম", "বাজেট", "সাশ্রয়ী", "সাশ্রয়ী"}
_PREMIUM_CUES = {"premium", "flagship", "luxury", "প্রিমিয়াম", "প্রিমিয়াম"}
_POPULAR_CUES = {"popular", "bestseller", "best-seller", "বেস্টসেলার", "জনপ্রিয়", "জনপ্রিয়"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\w\u0980-\u09ff.+#%-]+", text.casefold()) if len(t) > 1]


def is_recommendation_query(query: str) -> bool:
    q = query.casefold()
    tokens = set(_tokens(q))
    return bool(tokens & (_BEST_CUES | _PERFORMANCE_CUES | _VALUE_CUES | _PREMIUM_CUES | _POPULAR_CUES) or any(x in q for x in ("best seller", "best-seller", "সবচেয়ে ভালো", "সবচেয়ে ভালো")))


def _attribute_text(product) -> str:
    attrs = getattr(product, "attributes", None) or {}
    return " ".join(f"{k} {v}" for k, v in attrs.items()).casefold() if isinstance(attrs, dict) else ""


def _numeric_values(product) -> list[float]:
    values = []
    attrs = getattr(product, "attributes", None) or {}
    if not isinstance(attrs, dict): return values
    for value in attrs.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool): values.append(float(value))
        else:
            match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)", str(value))
            if match: values.append(float(match.group(1)))
    return values


def rank_products(products: Iterable, query: str) -> list:
    """Rank already-filtered products using query intent + merchant data."""
    items = list(products)
    if len(items) <= 1: return items
    q = query.casefold()
    qtokens = set(_tokens(q)) - _BEST_CUES
    performance = bool(qtokens & _PERFORMANCE_CUES)
    value = bool(qtokens & _VALUE_CUES)
    premium = bool(qtokens & _PREMIUM_CUES)
    popular = bool(qtokens & _POPULAR_CUES)
    prices = [float(p.price) for p in items if getattr(p, "price", None) is not None]
    lo, hi = (min(prices), max(prices)) if prices else (None, None)

    def price_value(p):
        if lo is None or hi is None or hi == lo or p.price is None: return 0.5
        return (hi - float(p.price)) / (hi - lo)

    def score(p):
        name = str(getattr(p, "name", "") or "").casefold()
        category = str(getattr(p, "category", "") or "").casefold()
        description = str(getattr(p, "description", "") or "").casefold()
        attrs = _attribute_text(p)
        searchable = f"{name} {category} {description} {attrs}"
        relevance = sum(1 for token in qtokens if token in searchable) / max(1, len(qtokens))
        stock_signal = 1.0 if getattr(p, "stock", None) is not None and float(p.stock) > 0 else 0.0
        completeness = min(1.0, len(getattr(p, "attributes", None) or {}) / 5.0)
        popularity_signal = 1.0 if any(cue in attrs for cue in _POPULAR_CUES) else 0.0
        performance_signal = 1.0 if any(cue in searchable for cue in _PERFORMANCE_CUES) else 0.0
        premium_signal = 1.0 if any(cue in searchable for cue in _PREMIUM_CUES) else 0.0
        if popular: return relevance * .45 + popularity_signal * .40 + stock_signal * .15
        if premium: return relevance * .45 + premium_signal * .40 + price_value(p) * .15
        if performance:
            nums = _numeric_values(p)
            numeric = min(1.0, max(nums) / 1000.0) if nums else 0.0
            return relevance * .55 + performance_signal * .30 + numeric * .15
        if value: return relevance * .55 + price_value(p) * .30 + completeness * .15
        return relevance * .55 + price_value(p) * .25 + completeness * .10 + stock_signal * .10

    return sorted(items, key=lambda p: (-score(p), str(getattr(p, "name", "")).casefold()))
