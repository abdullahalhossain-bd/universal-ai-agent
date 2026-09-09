"""Deterministic, merchant-data-driven recommendation ranking.

Ranking signals are intentionally conservative and evidence-based — the goal
is to never let the assistant claim a product is "best" on weaker grounds
than a careful human merchandiser would accept:

- **Bayesian rating shrinkage**: a single 5-star review must not outrank a
  product with hundreds of 4.6-star reviews. Small-sample ratings are pulled
  toward the catalog's observed mean until enough reviews accumulate.
- **Log-dampened popularity**: review/sales/bestseller counts are
  log-transformed before normalizing, so one viral outlier product doesn't
  flatten every other product's popularity score to near zero.
- **Stock-aware penalty**: an out-of-stock item is never hidden (a merchant
  may still want it discoverable), but it is multiplicatively deprioritized
  so the assistant doesn't recommend something a customer cannot buy today.
- **Variant diversification**: a top-10 list is capped on how many
  same-base-product variants (colour/size) it can hold before making room
  for genuinely different products, so "best laptop" doesn't come back as
  five colourways of the same SKU.
"""
from __future__ import annotations

import difflib
import math
import re
from typing import Iterable, Mapping

_BEST_CUES = {"best", "top", "recommend", "recommended", "suggest", "suggestion", "ভালো", "সেরা", "ভাল", "সর্বোত্তম", "সাজেস্ট", "রিকমেন্ড"}
_PERFORMANCE_CUES = {"performance", "powerful", "fast", "speed", "পারফরম্যান্স", "শক্তিশালী", "দ্রুত"}
_VALUE_CUES = {"value", "worth", "budget", "affordable", "দাম", "বাজেট", "সাশ্রয়ী"}
_PREMIUM_CUES = {"premium", "flagship", "luxury", "প্রিমিয়াম"}
_POPULAR_CUES = {"popular", "bestseller", "best-seller", "বেস্টসেলার", "জনপ্রিয়"}
_ALL_CUES = _BEST_CUES | _PERFORMANCE_CUES | _VALUE_CUES | _PREMIUM_CUES | _POPULAR_CUES


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\w\u0980-\u09ff.+#%-]+", text.casefold()) if len(t) > 1]


def _fuzzy_cue_matches(tokens, cues: set[str]) -> set[str]:
    """Match genuine cue words while avoiding false positives from tiny tokens."""
    matched: set[str] = set()
    for token in tokens:
        if token in cues:
            matched.add(token)
            continue
        # Two/three-character tokens are too ambiguous for fuzzy matching.
        # This prevents product names such as ``laptop`` from being interpreted
        # as recommendation cues merely because they contain/approach ``top``.
        if len(token) < 4:
            continue
        close = difflib.get_close_matches(token, cues, n=1, cutoff=0.78)
        if close:
            matched.add(token)
    return matched


def is_recommendation_query(query: str) -> bool:
    q = query.casefold()
    tokens = _tokens(q)
    if _fuzzy_cue_matches(tokens, _ALL_CUES):
        return True
    return any(x in q for x in ("best seller", "best-seller", "সবচেয়ে ভালো"))


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


def _log_signal(items, attr_name: str) -> dict[int, float]:
    """Log-dampened, 0..1 normalized popularity signal.

    A raw linear normalization (``value / max``) lets a single viral
    bestseller crush every other product's score toward zero even when
    those other products are also genuinely popular. ``log1p`` compresses
    the tail so the *relative ordering* of popular products still matters
    without one outlier dominating the whole catalog.
    """
    raw: dict[int, float] = {}
    for item in items:
        value = getattr(item, attr_name, None)
        try:
            value = float(value) if value is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and value > 0:
            raw[id(item)] = math.log1p(value)
    if not raw:
        return {}
    maximum = max(raw.values())
    if maximum <= 0:
        return {key: 0.0 for key in raw}
    return {key: value / maximum for key, value in raw.items()}


def _bayesian_rating_signal(items, prior_reviews: float = 8.0) -> dict[int, float]:
    """Shrink small-sample ratings toward the catalog's observed mean.

    Without this, a brand-new product with one 5-star review outranks a
    product with 500 reviews averaging 4.6 — a genuinely bad recommendation
    that erodes merchant/customer trust. The shrinkage weight
    (``prior_reviews``) means a product needs real review volume before its
    raw rating is trusted at face value; sparse-review products are pulled
    toward the average until evidence accumulates.
    """
    pairs = []
    for item in items:
        rating = getattr(item, "rating", None)
        try:
            rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None
        if rating is None or not 0 <= rating <= 5:
            continue
        reviews = getattr(item, "review_count", None)
        try:
            reviews = max(0.0, float(reviews)) if reviews is not None else 0.0
        except (TypeError, ValueError):
            reviews = 0.0
        pairs.append((item, rating, reviews))
    if not pairs:
        return {}
    global_mean = sum(rating for _, rating, _ in pairs) / len(pairs)
    signal: dict[int, float] = {}
    for item, rating, reviews in pairs:
        shrunk = ((reviews * rating) + (prior_reviews * global_mean)) / (reviews + prior_reviews)
        signal[id(item)] = max(0.0, min(1.0, shrunk / 5.0))
    return signal


_VARIANT_WORDS = {
    "red", "blue", "green", "black", "white", "yellow", "grey", "gray", "pink",
    "purple", "orange", "brown", "silver", "gold", "navy", "maroon", "beige",
    "small", "medium", "large", "xl", "xxl", "xs", "s", "m", "l",
    "লাল", "নীল", "সবুজ", "কালো", "সাদা", "হলুদ", "সোনালি", "রুপালি",
    "ছোট", "মাঝারি", "বড়",
}


def _base_name(name: str) -> str:
    """Collapse a product name to its variant-independent base.

    Strips a trailing colour/size qualifier and anything after a common
    variant separator (``-``, ``(``, ``:``), so "T-Shirt - Red" and
    "T-Shirt (Blue, L)" collapse to the same base while genuinely distinct
    products keep their own identity.
    """
    name = (name or "").casefold()
    for sep in (" - ", " – ", "(", "|", ":", ","):
        if sep in name:
            name = name.split(sep, 1)[0]
    tokens = [t for t in _tokens(name) if t not in _VARIANT_WORDS]
    return " ".join(tokens).strip()


def _diversify_variants(ranked: list, max_per_base: int = 2) -> list:
    """Keep score order, but stop letting one product's colour/size variants
    monopolize the results — cap same-base-product repeats and push the rest
    later so genuinely different products still surface near the top.

    Never drops an item; only reorders. Safe to apply after any scoring.
    """
    if len(ranked) <= max_per_base:
        return ranked
    seen: dict[str, int] = {}
    kept, deferred = [], []
    for item in ranked:
        key = f"{_base_name(str(getattr(item, 'name', '') or ''))}|{str(getattr(item, 'category', '') or '').casefold()}"
        count = seen.get(key, 0)
        if count < max_per_base:
            kept.append(item)
            seen[key] = count + 1
        else:
            deferred.append(item)
    return kept + deferred


def _stock_penalty(product) -> float:
    """Multiplicative deprioritization for known-empty stock.

    Unknown stock (``None`` — merchant doesn't track it) is never
    penalized. Only an explicit ``stock <= 0`` is treated as evidence the
    item can't be bought right now, so it rarely leads a recommendation
    even if every other signal favors it.
    """
    stock = getattr(product, "stock", None)
    try:
        stock = float(stock) if stock is not None else None
    except (TypeError, ValueError):
        stock = None
    return 0.6 if stock is not None and stock <= 0 else 1.0


def rank_products(products: Iterable, query: str, behavior_scores: Mapping[str, float] | None = None) -> list:
    """Rank already-filtered products using query intent + verified merchant data."""
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
    rating_signal = _bayesian_rating_signal(items)
    review_signal = _log_signal(items, "review_count")
    sales_signal = _log_signal(items, "sales_count")
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
        dedicated_popularity = (bestseller_signal.get(id(p), 0.0) * 0.45 + sales_signal.get(id(p), 0.0) * 0.35 + review_signal.get(id(p), 0.0) * 0.20)
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
        return relevance * .55 + evidence_signal * .20 + behavior * .12 + price_value(p) * .06 + completeness * .05 + stock_signal * .02

    def final_score(p):
        # Stock is a multiplicative gate, not an additive bonus: an
        # out-of-stock item should lose even if every other signal (rating,
        # popularity, relevance) favors it — a "best" recommendation the
        # customer can't actually buy is a worse answer than a slightly
        # weaker in-stock alternative.
        return score(p) * _stock_penalty(p)

    ranked = sorted(items, key=lambda p: (-final_score(p), str(getattr(p, "name", "")).casefold()))
    return _diversify_variants(ranked)
