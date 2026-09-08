from app.connectors.field_scoring import score_column, FIELD_NAME_HINTS


def build_candidate_mapping(columns: list[dict]):
    """Build ranked candidates from the single canonical field registry."""
    mapping = {}

    for field in FIELD_NAME_HINTS:
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
                    "score": score,
                })
        candidates.sort(key=lambda item: item["score"], reverse=True)
        mapping[field] = candidates

    return mapping


def resolve_mapping(candidate_mapping: dict, auto_threshold: float = 0.80):
    """Resolve a one-to-one mapping without allowing one column to fill many fields.

    Exact canonical aliases are accepted at high confidence. Ambiguous columns are
    left for confirmation instead of silently producing an invalid mapping.
    """
    resolved = {}
    needs_confirmation = {}
    used_columns = set()

    # Highest-confidence fields get first claim on a source column.
    fields = sorted(
        candidate_mapping,
        key=lambda field: (
            candidate_mapping[field][0]["score"]
            if candidate_mapping[field] else 0,
            field,
        ),
        reverse=True,
    )

    for field in fields:
        candidates = [
            candidate for candidate in candidate_mapping.get(field, [])
            if candidate["column"] not in used_columns
        ]

        if not candidates:
            continue

        best = candidates[0]
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        margin = best["score"] - second_score

        # High score plus a useful margin is safe to auto-accept. Exact alias
        # matches score >= .70; do not require type evidence for obvious names.
        if best["score"] >= auto_threshold or (
            best["score"] >= 0.70 and margin >= 0.10
        ):
            resolved[field] = {
                "column": best["column"],
                "confidence": best["score"],
            }
            used_columns.add(best["column"])
        else:
            needs_confirmation[field] = candidates

    return {
        "resolved": resolved,
        "needs_confirmation": needs_confirmation,
    }
