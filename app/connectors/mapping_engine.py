from app.connectors.field_hints import FIELD_HINTS
from app.connectors.field_scoring import score_column
from app.connectors.mapping_candidates import MappingCandidate


class MappingEngine:
    """Backward-compatible facade over the unified mapping scorer."""

    def suggest(self, columns: list[str]):
        results = []

        for field in FIELD_HINTS:
            candidates = []
            for column in columns:
                score = score_column(field, column)
                if score > 0:
                    candidates.append(
                        MappingCandidate(
                            field=field,
                            column=column,
                            confidence=score,
                            reason="Column name/type pattern matched canonical ecommerce field",
                        )
                    )

            candidates.sort(key=lambda item: item.confidence, reverse=True)
            if candidates:
                results.append(candidates[0])

        return results
