from app.connectors.field_hints import (
    FIELD_HINTS,
)

from app.connectors.normalizer import (
    normalize_name,
)

from app.connectors.mapping_candidates import (
    MappingCandidate,
)


class MappingEngine:

    def suggest(
        self,
        columns: list[str],
    ):

        results = []

        normalized = {
            column: normalize_name(column)
            for column in columns
        }

        for field, hints in (
            FIELD_HINTS.items()
        ):

            candidates = []

            for column, name in (
                normalized.items()
            ):

                score = self._score(
                    name,
                    hints,
                )

                if score > 0:

                    candidates.append(
                        MappingCandidate(
                            field=field,
                            column=column,
                            confidence=score,
                            reason=(
                                "Column name "
                                "matched known "
                                "field pattern"
                            ),
                        )
                    )

            candidates.sort(
                key=lambda x: x.confidence,
                reverse=True,
            )

            if candidates:

                results.append(
                    candidates[0]
                )

        return results

    def _score(
        self,
        column: str,
        hints: set[str],
    ):

        if column in hints:

            return 0.95

        for hint in hints:

            if (
                hint in column
                or column in hint
            ):

                return 0.75

        return 0.0
