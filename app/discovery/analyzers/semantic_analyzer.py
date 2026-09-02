import re

from app.discovery.models import (
    ColumnSample,
    SemanticMapping,
)

from app.discovery.analyzers.value_analyzer import (
    ValueAnalyzer,
)


PATTERNS = {
    "id": [
        r"^id$",
        r"(^|_)id$",
        r"^pid$",
        r"^product_id$",
        r"^item_id$",
    ],

    "name": [
        r"^name$",
        r"(^|_)name$",
        r"^title$",
        r"product_name",
        r"item_name",
        r"pname",
    ],

    "price": [
        r"price",
        r"amount",
        r"cost",
        r"selling_amt",
        r"selling_price",
        r"sale_price",
    ],

    "stock": [
        r"stock",
        r"quantity",
        r"qty",
        r"inventory",
        r"available",
        r"qty_available",
    ],

    "image": [
        r"image",
        r"img",
        r"photo",
        r"picture",
        r"thumbnail",
    ],

    "url": [
        r"url",
        r"link",
        r"product_url",
        r"permalink",
    ],

    "description": [
        r"description",
        r"details",
        r"summary",
        r"content",
    ],

    "category": [
        r"category",
        r"category_id",
        r"product_category",
    ],

    "brand": [
        r"brand",
        r"brand_name",
        r"manufacturer",
    ],
}


class SemanticAnalyzer:

    def __init__(self):
        self.value_analyzer = ValueAnalyzer()

    def analyze(
        self,
        columns: list[ColumnSample],
    ) -> list[SemanticMapping]:

        results = []

        for column in columns:

            name = column.column.lower()

            value_signals = (
                self.value_analyzer.analyze(
                    column.samples,
                    column.data_type,
                )
            )

            candidates = []

            for semantic_type, patterns in PATTERNS.items():

                score = self._name_score(
                    name,
                    patterns,
                )

                evidence = []

                if score > 0:
                    evidence.append(
                        "column-name-match"
                    )

                if semantic_type == "image":
                    if "image_path" in value_signals:
                        score += 0.20
                        evidence.append(
                            "image-like-values"
                        )

                if semantic_type == "url":
                    if "url" in value_signals:
                        score += 0.20
                        evidence.append(
                            "url-like-values"
                        )

                if semantic_type == "price":
                    if "numeric" in value_signals:
                        score += 0.10
                        evidence.append(
                            "numeric-values"
                        )

                if semantic_type == "stock":
                    if "numeric" in value_signals:
                        score += 0.08
                        evidence.append(
                            "numeric-values"
                        )

                score = min(score, 0.99)

                if score > 0:
                    candidates.append(
                        SemanticMapping(
                            table=column.table,
                            column=column.column,
                            semantic_type=semantic_type,
                            confidence=score,
                            evidence=evidence,
                        )
                    )

            results.extend(candidates)

        return results

    @staticmethod
    def _name_score(
        name: str,
        patterns: list[str],
    ) -> float:

        best = 0.0

        for pattern in patterns:

            if re.search(pattern, name):

                if (
                    pattern.startswith("^")
                    or pattern == name
                ):
                    best = max(best, 0.88)
                else:
                    best = max(best, 0.75)

        return best
