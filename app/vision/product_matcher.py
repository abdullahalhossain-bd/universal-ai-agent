"""
ProductMatcher — ranks a store's catalog against a `VisionService`
analysis result (category / colors / keywords / brand).

Deliberately simple keyword scoring rather than embeddings/ANN: the
attributes coming out of vision analysis are already short, curated
terms (see the JSON schema requested in
`app.vision.vision_router._PRODUCT_MATCH_PROMPT`), so a scored
substring match against `Product.name`/`description` gives
reasonable results without a vector index. If this needs to get
smarter later, it's the same shape as `app.search.synonyms` /
`app.search.ranking` used by text search — swap the scoring function,
keep the store-scoping.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Product


class ProductMatcher:

    def __init__(self, db: Session):
        self.db = db

    def match(
        self,
        *,
        store_id: str,
        analysis: dict,
        limit: int = 5,
    ) -> list[Product]:

        terms = self._extract_terms(analysis)

        if not terms:
            return []

        candidates = (
            self.db.query(Product)
            .filter(Product.store_id == store_id)
            .all()
        )

        scored = []

        for product in candidates:

            haystack = " ".join(
                part
                for part in (product.name, product.description)
                if part
            ).lower()

            score = sum(
                1 for term in terms if term and term in haystack
            )

            if score > 0:
                scored.append((score, product))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        return [product for _, product in scored[:limit]]

    def _extract_terms(self, analysis: dict) -> list[str]:

        terms: list[str] = []

        category = analysis.get("category")
        if category:
            terms.append(str(category).strip().lower())

        brand = analysis.get("brand")
        if brand:
            terms.append(str(brand).strip().lower())

        for color in analysis.get("colors") or []:
            if color:
                terms.append(str(color).strip().lower())

        for keyword in analysis.get("keywords") or []:
            if keyword:
                terms.append(str(keyword).strip().lower())

        return [term for term in terms if len(term) >= 2]
