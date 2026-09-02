import re

from app.discovery.models import (
    DatabaseSchema,
    FieldCandidate,
)


FIELD_PATTERNS = {
    "id": [
        r"^id$",
        r".*_id$",
        r"^product_id$",
        r"^item_id$",
        r"^sku$",
    ],
    "name": [
        r"^name$",
        r".*_name$",
        r"^title$",
        r"product_name",
        r"item_name",
    ],
    "price": [
        r"price",
        r"amount",
        r"cost",
        r"selling_price",
        r"sale_price",
    ],
    "stock": [
        r"stock",
        r"quantity",
        r"qty",
        r"inventory",
        r"available",
    ],
    "image": [
        r"image",
        r"img",
        r"photo",
        r"picture",
    ],
    "url": [
        r"url",
        r"link",
        r"slug",
    ],
    "description": [
        r"description",
        r"details",
        r"summary",
        r"content",
    ],
}


class FieldAnalyzer:

    def analyze(
        self,
        schema: DatabaseSchema,
    ) -> list[FieldCandidate]:

        candidates = []

        for table in schema.tables:

            for column in table.columns:

                column_name = column.name.lower()

                for semantic_type, patterns in FIELD_PATTERNS.items():

                    confidence = self._calculate_confidence(
                        column_name,
                        patterns,
                    )

                    if confidence > 0:

                        candidates.append(
                            FieldCandidate(
                                table=table.name,
                                column=column.name,
                                semantic_type=semantic_type,
                                confidence=confidence,
                                reason=(
                                    f"Column name matched "
                                    f"{semantic_type} pattern"
                                ),
                            )
                        )

        return candidates

    @staticmethod
    def _calculate_confidence(
        name: str,
        patterns: list[str],
    ) -> float:

        best = 0.0

        for pattern in patterns:

            if re.search(pattern, name):

                if name == pattern.replace("^", "").replace("$", ""):
                    best = max(best, 0.98)
                else:
                    best = max(best, 0.85)

        return best
