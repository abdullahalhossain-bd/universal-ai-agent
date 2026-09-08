from app.connectors.field_scoring import (
    score_column,
    FIELD_NAME_HINTS,
)


def build_candidate_mapping(
    columns: list[dict],
):
    """
    columns: list of {
        "name": str,
        "type": str | None,
        "samples": list | None,
    }
    """

    mapping = {}

    for field in FIELD_NAME_HINTS.keys():

        candidates = []

        for col in columns:

            score = score_column(
                field=field,
                column_name=col["name"],
                column_type=col.get("type"),
                sample_values=col.get("samples"),
            )

            if score > 0:

                candidates.append({
                    "column": col["name"],
                    "score": round(score, 2),
                })

        candidates.sort(
            key=lambda c: c["score"],
            reverse=True,
        )

        mapping[field] = candidates

    return mapping


def resolve_mapping(
    candidate_mapping: dict,
    auto_threshold: float = 0.85,
):

    resolved = {}

    needs_confirmation = {}

    for field, candidates in candidate_mapping.items():

        if not candidates:
            continue

        best = candidates[0]

        if best["score"] >= auto_threshold:

            resolved[field] = {
                "column": best["column"],
                "confidence": best["score"],
            }

        else:

            needs_confirmation[field] = candidates

    return {
        "resolved": resolved,
        "needs_confirmation": needs_confirmation,
    }
