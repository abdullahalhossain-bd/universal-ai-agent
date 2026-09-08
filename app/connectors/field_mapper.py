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

    Strong canonical names/aliases remain eligible even when another field also
    wants the same column. The global allocator resolves that contention. Weak
    fuzzy candidates still require the configured threshold and a clear margin.
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
    """Find an exact maximum-weight one-to-one field/column assignment.

    Hungarian matching is implemented locally to avoid adding a dependency just
    for datasource mapping. Dummy columns represent an intentionally unresolved
    field, so the optimizer can choose fewer mappings when that is safer.
    """
    fields = [field for field, candidates in eligible.items() if candidates]
    columns = sorted({candidate["column"] for candidates in eligible.values() for candidate in candidates})

    if not fields or not columns:
        return {}

    # We need at least one dummy column per field so every field can remain
    # unresolved when no real source column is worth assigning to it.
    real_column_count = len(columns)
    dummy_count = len(fields)
    matrix_columns = columns + [f"__unmatched_{index}" for index in range(dummy_count)]
    column_index = {column: index for index, column in enumerate(matrix_columns)}

    # Hungarian algorithm solves a minimum-cost assignment for n <= m. Ineligible
    # real edges receive a very large cost; dummy edges have zero cost.
    n = len(fields)
    m = len(matrix_columns)
    inf = 10**9
    costs = [[0.0] * (m + 1) for _ in range(n + 1)]
    score_lookup = {}

    for row, field in enumerate(fields, start=1):
        candidates_by_column = {candidate["column"]: candidate["score"] for candidate in eligible[field]}
        for column, index in column_index.items():
            col = index + 1
            if column.startswith("__unmatched_"):
                costs[row][col] = 0.0
                continue
            score = candidates_by_column.get(column)
            if score is None:
                costs[row][col] = inf
                continue
            # Scores are rounded to 4 decimals, so this tiny priority bonus only
            # breaks genuine score ties in favor of primary product fields.
            weight = score + FIELD_PRIORITY.get(field, 0) * 1e-7
            costs[row][col] = -weight
            score_lookup[(field, column)] = score

    # Standard 1-indexed Hungarian implementation.
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = costs[i0][j] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assignment = {}
    for j in range(1, m + 1):
        row = p[j]
        if row == 0 or row > n:
            continue
        field = fields[row - 1]
        column = matrix_columns[j - 1]
        if column in score_lookup and score_lookup[(field, column)] >= 0:
            assignment[field] = column

    # The optimizer can choose a dummy column for every field; only real source
    # columns are returned, guaranteeing global one-to-one ownership.
    return assignment


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
