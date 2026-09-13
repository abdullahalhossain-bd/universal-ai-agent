"""Deterministic, catalog-grounded product recommendation ranking.

The recommender never invents product facts and never requires an LLM. It ranks
already-matched catalog products using the strongest signals actually available
for each product, while gracefully degrading when merchants have sparse data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationResult:
    product: object
    score: float
    reasons: tuple[str, ...]


def _float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _positive(value) -> float:
    value = _float(value)
    return value if value is not None and value > 0 else 0.0


def _normalize(values: list[float]) -> dict[float, float]:
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi <= lo:
        return {value: 0.5 for value in values}
    return {value: (value - lo) / (hi - lo) for value in values}


def rank_products(products: list, *, max_price: float | None = None) -> list:
    """Rank products for a "best/recommend" request.

    Signal weights are intentionally conservative:
    - rating quality (Bayesian shrinkage) is strongest when reviews exist;
    - review volume provides confidence without letting raw count dominate;
    - sales and merchant bestseller score capture popularity when available;
    - stock is a small positive signal, never a substitute for relevance;
    - price gets a gentle preference for value, especially under a budget.

    Missing merchant signals are ignored/re-normalized rather than treated as
    bad products. Ties preserve the original DB relevance order.
    """
    if not products:
        return []
    if len(products) == 1:
        return products

    ratings = [_float(getattr(p, "rating", None)) for p in products]
    review_counts = [_positive(getattr(p, "review_count", None)) for p in products]
    sales_counts = [_positive(getattr(p, "sales_count", None)) for p in products]
    bestseller = [_float(getattr(p, "bestseller_score", None)) for p in products]

    valid_ratings = [r for r in ratings if r is not None and 0 <= r <= 5]
    global_mean = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 3.5
    prior_reviews = 8.0

    bayesian_quality: list[float | None] = []
    for rating, reviews in zip(ratings, review_counts):
        if rating is None or not 0 <= rating <= 5:
            bayesian_quality.append(None)
            continue
        # Shrink small-sample ratings toward the catalog's observed mean.
        quality = ((reviews * rating) + (prior_reviews * global_mean)) / (reviews + prior_reviews)
        bayesian_quality.append(max(0.0, min(1.0, quality / 5.0)))

    # Log transforms prevent one very popular item from overwhelming every
    # other signal. Normalize only among values that actually exist.
    log_reviews = [math.log1p(v) if v > 0 else 0.0 for v in review_counts]
    log_sales = [math.log1p(v) if v > 0 else 0.0 for v in sales_counts]
    review_norm = _normalize([v for v in log_reviews if v > 0])
    sales_norm = _normalize([v for v in log_sales if v > 0])

    valid_best = [v for v in bestseller if v is not None]
    best_norm = _normalize(valid_best)

    prices = [_float(getattr(p, "price", None)) for p in products]
    valid_prices = [p for p in prices if p is not None and p >= 0]
    price_norm = _normalize(valid_prices)

    scored: list[RecommendationResult] = []

    for index, product in enumerate(products):
        components: list[tuple[float, float]] = []
        reasons: list[str] = []

        quality = bayesian_quality[index]
        if quality is not None:
            components.append((0.40, quality))
            if quality >= 0.82:
                reasons.append("strong rating quality")
            elif quality >= 0.70:
                reasons.append("good rating quality")

        if log_reviews[index] > 0:
            components.append((0.12, review_norm.get(log_reviews[index], 0.5)))
            if review_counts[index] >= 20:
                reasons.append("well reviewed")

        if log_sales[index] > 0:
            components.append((0.18, sales_norm.get(log_sales[index], 0.5)))
            if sales_counts[index] > 0:
                reasons.append("popular with buyers")

        if bestseller[index] is not None:
            # Treat merchant bestseller_score as an explicit signal, but do
            # not let it dominate objective customer evidence.
            components.append((0.15, best_norm.get(bestseller[index], 0.5)))
            if bestseller[index] > 0:
                reasons.append("merchant popularity signal")

        stock = _float(getattr(product, "stock", None))
        if stock is not None and stock > 0:
            components.append((0.05, 1.0))
            reasons.append("currently in stock")

        price = prices[index]
        if price is not None and price >= 0 and valid_prices:
            if max_price is not None and max_price > 0:
                # Under a budget, reward products comfortably within budget,
                # with the strongest value signal around ~65% of the ceiling.
                ratio = price / max_price
                value = 1.0 if ratio <= 0.65 else max(0.0, 1.0 - (ratio - 0.65) / 0.35)
                components.append((0.10, value))
                if ratio <= 0.85:
                    reasons.append("good budget fit")
            else:
                # No stated budget: a mild value preference only. Never rank
                # purely by cheapness.
                components.append((0.05, 1.0 - price_norm.get(price, 0.5)))

        if not components:
            # Sparse catalog: preserve relevance/order instead of pretending
            # that missing data is a meaningful negative signal.
            score = 0.0
        else:
            weight_total = sum(weight for weight, _ in components)
            score = sum(weight * value for weight, value in components) / weight_total

        scored.append(
            RecommendationResult(
                product=product,
                score=score,
                reasons=tuple(dict.fromkeys(reasons))[:3],
            )
        )

    scored.sort(key=lambda item: (-item.score, products.index(item.product)))
    return [item.product for item in scored]
