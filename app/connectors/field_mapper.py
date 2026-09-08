from app.connectors.field_scoring import score_column, FIELD_NAME_HINTS


DEFAULT_AUTO_THRESHOLD = 0.80
EXACT_ALIAS_THRESHOLD = 0.90

# Stable tie-break order for aliases that legitimately overlap (for example
# ``regular_price`` can mean either price or compare-at/original price).
# Primary product fields win ties over derived/secondary fields.
FIELD_PRIORITY = {
    "id": 100,
    "name": 99,
    "sku": 98,
    "barcode": 97,
    "price": 96,
    "stock": 95,
    "availability": 94,
    "image": 93,
    "images": 92,
    "url": 91,
    "description": 90,
    "brand": 89,
    "category": 88,
    "subcategory": 87,
    "currency": 86,
    "tags": 85,
    "color": 84,
    "size": 83,
    "material": 82,
    "variant": 81,
    "weight": 80,
    "rating": 79,
    "review_count": 78,
    "discount": 77,
    "created_at": 76,
    "updated_at": 75,
    "compare_at_price": 70,
}


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
        candidates.sort(
            key=lambda item: (item["score"], item["column"]),
            reverse=True,
        )
        mapping[field] = candidates

    return mapping


def _eligible_candidates(candidate_mapping: dict, auto_threshold: float):
    """Return candidates that are strong enough for automatic assignment.

    Exact canonical names/aliases are eligible at the strong alias threshold.
    Lower-confidence candidates need both the configured threshold and a clear
    margin over the next candidate for that field. This keeps weak fuzzy matches
    out of automatic mapping while allowing the global allocator to resolve
    genuine column contention.
    """
    eligible = {}

    for field, candidates in candidate_mapping.items():
        if not candidates:
            eligible[field] = []
            continue

        strong = [
            candidate
            for candidate in candidates
            if candidate["score"] >= max(auto_threshold, EXACT_ALIAS_THRESHOLD)
        ]
        if strong:
            eligible[field] = strong
            continue

        best = candidates[0]
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        if best["score"] >= auto_threshold and best["score"] - second_score >= 0.10:
            eligible[field] = [best]
        else:
            eligible[field] = []

    return eligible


def _maximum_weight_matching(eligible: dict):
    """Find a deterministic maximum-weight field -> source-column assignment.

    This is a dependency-free weighted bipartite matcher. For normal ecommerce
    schemas the contested candidate graph is small, so an exact bitmask dynamic
    program finds the global optimum rather than making a greedy local choice.
    A deterministic edge-order fallback protects against pathological graphs.
    """
    fields = [field for field, candidates in eligible.items() if candidates]
    columns = sorted({candidate["column"] for candidates in eligible.values() for candidate in candidates})

    if not fields or not columns:
        return {}

    if len(columns) <= 22:
        column_index = {column: index for index, column in enumerate(columns)}
        options = {}
        for field in fields:
            options[field] = [
                (column_index[candidate["column"]], candidate["score"])
                for candidate in eligible[field]
            ]

        memo = {}
        unmatched_token = len(columns) + 1

        def better(left, right):
            if right is None:
                return True
            left_score, left_count, left_key = left
            right_score, right_count, right_key = right
            if left_score != right_score:
                return left_score > right_score
            if left_count != right_count:
                return left_count > right_count
            return left_key < right_key

        def solve(index, used_mask):
            key = (index, used_mask)
            if key in memo:
                return memo[key]
            if index == len(fields):
                result = (0.0, 0, ())
                memo[key] = result
                return result

            field = fields[index]
            best_tail = solve(index + 1, used_mask)
            best = (
                best_tail[0],
                best_tail[1],
                (unmatched_token,) + best_tail[2],
            )

            for column_idx, score in options[field]:
                bit = 1 << column_idx
                if used_mask & bit:
                    continue
                tail = solve(index + 1, used_mask | bit)
                priority_bonus = FIELD_PRIORITY.get(field, 0) * 1e-7
                candidate = (
                    score + tail[0] + priority_bonus,
                    1 + tail[1],
                    (column_idx,) + tail[2],
                )
                if better(candidate, best):
                    best = candidate

            memo[key] = best
            return best

        assignment = solve(0, 0)[2]
        return {
            field: columns[column_idx]
            for field, column_idx in zip(fields, assignment)
            if column_idx != unmatched_token
        }

    # Defensive fallback for very large candidate graphs. It still guarantees
    # one-to-one ownership and is deterministic, while normal ecommerce schemas
    # use the exact path above.
    edges = []
    for field in fields:
        for candidate in eligible[field]:
            edges.append((candidate["score"], FIELD_PRIORITY.get(field, 0), field, candidate["column"]))
    edges.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)

    resolved = {}
    used_columns = set()
    used_fields = set()
    for score, _priority, field, column in edges:
        if field in used_fields or column in used_columns:
            continue
        resolved[field] = column
        used_fields.add(field)
        used_columns.add(column)
    return resolved


def resolve_mapping(
    candidate_mapping: dict,
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
):
    """Resolve a globally optimal one-to-one automatic datasource mapping."""
    if not 0.0 <= auto_threshold <= 1.0:
        raise ValueError("auto_threshold must be between 0 and 1")

    eligible = _eligible_candidates(candidate_mapping, auto_threshold)
    assignment = _maximum_weight_matching(eligible)

    resolved = {}
    used_columns = set(assignment.values())
    for field, column in assignment.items():
        candidate = next(
            candidate
            for candidate in eligible[field]
            if candidate["column"] == column
        )
        resolved[field] = {
            "column": column,
            "confidence": candidate["score"],
        }

    needs_confirmation = {}
    for field, candidates in candidate_mapping.items():
        if field in resolved:
            continue
        available = [
            candidate
            for candidate in candidates
            if candidate["column"] not in used_columns
        ]
        if available:
            needs_confirmation[field] = available

    return {
        "resolved": resolved,
        "needs_confirmation": needs_confirmation,
    }
