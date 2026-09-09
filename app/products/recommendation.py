"""Deterministic, merchant-data-driven recommendation ranking."""
from __future__ import annotations

import re
from typing import Iterable, Mapping

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


def _relative_signal(items, attr_name: str) -> dict[int, float]:
    values = {}
    for item in items:
        value = getattr(item, attr_name, None)
        try:
            if value is not None:
                values[id(item)] = max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return {}
    maximum = max(values.values())
    if maximum <= 0:
        return {key: 0.0 for key in values}
    return {key: value / maximum for key, value in values.items()}


def rank_products(products: Iterable, query: str, behavior_scores: Mapping[str, float] | None = None) -> list:
    """Rank already-filtered products using query intent + verified merchant data.

    Behavioral evidence is an additional ranking signal only when observed.
    It is store-scoped by the caller and never treated as a fabricated rating.
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
    lo, hi = (min(prices), max(prices)) if prices else (None, None)
    rating_signal = _relative_signal(items, "rating")
    review_signal = _relative_signal(items, "review_count")
    sales_signal = _relative_signal(items, "sales_count")
    bestseller_signal = _relative_signal(items, "bestseller_score")
    observed_behavior = behavior_scores or {}
    behavior_values = [max(0.0, float(v)) for v in observed_behavior.values() if v is not None]
    behavior_max = max(behavior_values, default=0.0)

    def price_value(p):
        if lo is None or hi is None or hi == lo or p.price is None:
            return 0.5
        return (hi - float(p.price)) / (hi - lo)

    def behavior_signal(p):
        if behavior_max <= 0:
            return 0.0
        return min(1.0, max(0.0, float(observed_behavior.get(str(p.id), 0.0))) / behavior_max)

    def score(p):
        name = str(getattr(p, "name", "") or "").casefold()
        category = str(getattr(p, "category", "") or "").casefold()
        description = str(getattr(p, "description", "") or "").casefold()
        attrs = _attribute_text(p)
        searchable = f"{name} {category} {description} {attrs}"
        relevance = sum(1 for token in qtokens if token in searchable) / max(1, len(qtokens))
        stock_signal = 1.0 if getattr(p, "stock", None) is not None and float(p.stock) > 0 else 0.0
        completeness = min(1.0, len(getattr(p, "attributes", None) or {}) / 5.0)

        dedicated_popularity = (
            bestseller_signal.get(id(p), 0.0) * 0.45
            + sales_signal.get(id(p), 0.0) * 0.35
            + review_signal.get(id(p), 0.0) * 0.20
        )
        merchant_popularity = 1.0 if any(cue in attrs for cue in _POPULAR_CUES) else 0.0
        popularity_evidence = max(dedicated_popularity, merchant_popularity)
        performance_signal = 1.0 if any(cue in searchable for cue in _PERFORMANCE_CUES) else 0.0
        premium_signal = 1.0 if any(cue in searchable for cue in _PREMIUM_CUES) else 0.0
        behavior = behavior_signal(p)

        if popular:
            return relevance * .40 + popularity_evidence * .35 + behavior * .20 + stock_signal * .05
        if premium:
            return relevance * .42 + premium_signal * .23 + price_value(p) * .15 + rating_signal.get(id(p), 0.0) * .10 + behavior * .10
        if performance:
            nums = _numeric_values(p)
            numeric = min(1.0, max(nums) / 1000.0) if nums else 0.0
            return relevance * .48 + performance_signal * .22 + numeric * .10 + rating_signal.get(id(p), 0.0) * .10 + behavior * .10
        if value:
            return relevance * .46 + price_value(p) * .24 + rating_signal.get(id(p), 0.0) * .12 + behavior * .10 + completeness * .08

        quality_signal = rating_signal.get(id(p), 0.0)
        evidence_signal = max(quality_signal, popularity_evidence)
        return relevance * .42 + evidence_signal * .23 + behavior * .15 + price_value(p) * .12 + completeness * .06 + stock_signal * .02

    return sorted(items, key=lambda p: (-score(p), str(getattr(p, "name", "")).casefold()))
