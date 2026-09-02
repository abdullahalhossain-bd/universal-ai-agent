from collections import defaultdict

from app.discovery.models import (
    MappingQuestion,
    SemanticMapping,
)


STRICT_TYPES = {
    "id",
    "price",
    "stock",
}


class ConfidenceEngine:

    def process(
        self,
        mappings: list[SemanticMapping],
    ) -> tuple[
        list[SemanticMapping],
        list[MappingQuestion],
    ]:

        grouped = defaultdict(list)

        for mapping in mappings:
            grouped[
                (
                    mapping.table,
                    mapping.semantic_type,
                )
            ].append(mapping)

        questions = []

        for key, items in grouped.items():

            table, semantic_type = key

            items.sort(
                key=lambda x: x.confidence,
                reverse=True,
            )

            threshold = (
                0.90
                if semantic_type in STRICT_TYPES
                else 0.80
            )

            for index, item in enumerate(items):

                if index == 0 and item.confidence >= threshold:

                    item.status = "accepted"

                elif item.confidence >= 0.50:

                    item.status = "needs_review"

                else:

                    item.status = "unknown"

            review_items = [
                item
                for item in items
                if item.status == "needs_review"
            ]

            accepted = [
                item
                for item in items
                if item.status == "accepted"
            ]

            # If we have an accepted mapping and
            # another weak alternative, don't bother
            # the merchant unnecessarily.

            if accepted:
                continue

            if review_items:

                questions.append(
                    MappingQuestion(
                        semantic_type=semantic_type,
                        candidates=review_items,
                        question=(
                            f"Which field represents "
                            f"{semantic_type}?"
                        ),
                    )
                )

        return mappings, questions
