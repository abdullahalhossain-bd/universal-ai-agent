from app.connectors.field_scoring import score_column, FIELD_NAME_HINTS


DEFAULT_AUTO_THRESHOLD = 0.80
EXACT_ALIAS_THRESHOLD = 0.90


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


def resolve_mapping(
    candidate_mapping: dict,
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
):
    """Resolve a one-to-one mapping using confidence and ambiguity checks.

    The threshold remains configurable, but obvious canonical names/aliases are
    auto-accepted by the scorer at >= 0.90. Medium-confidence matches require a
    meaningful margin over the next candidate so ambiguous ecommerce columns do
    not get silently assigned.
    """
    if not 0.0 <= auto_threshold <= 1.0:
        raise ValueError("auto_threshold must be between 0 and 1")

    resolved = {}
    needs_confirmation = {}
    used_columns = set()

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
            candidate
            for candidate in candidate_mapping.get(field, [])
            if candidate["column"] not in used_columns
        ]

        if not candidates:
            continue

        best = candidates[0]
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        margin = best["score"] - second_score

        # Strong canonical evidence: auto-map even when no sample/type metadata
        # is available. This is the important fix for sparse datasource schemas.
        if best["score"] >= max(auto_threshold, EXACT_ALIAS_THRESHOLD):
            resolved[field] = {
                "column": best["column"],
                "confidence": best["score"],
            }
            used_columns.add(best["column"])
            continue

        # Medium confidence is only automatic when clearly better than alternatives.
        if best["score"] >= auto_threshold and margin >= 0.10:
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
