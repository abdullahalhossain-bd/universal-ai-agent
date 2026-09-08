from app.connectors.field_scoring import score_column, FIELD_NAME_HINTS


DEFAULT_AUTO_THRESHOLD = 0.80
EXACT_ALIAS_THRESHOLD = 0.90

FIELD_PRIORITY = {
    "id": 100, "name": 99, "sku": 98, "barcode": 97, "price": 96,
    "stock": 95, "availability": 94, "image": 93, "images": 92, "url": 91,
    "description": 90, "brand": 89, "category": 88, "subcategory": 87,
    "currency": 86, "tags": 85, "color": 84, "size": 83, "material": 82,
    "variant": 81, "weight": 80, "rating": 79, "review_count": 78,
    "discount": 77, "created_at": 76, "updated_at": 75, "compare_at_price": 70,
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
                candidates.append({"column": col["name"], "score": score})
        candidates.sort(key=lambda item: (item["score"], item["column"]), reverse=True)
        mapping[field] = candidates
    return mapping


def _eligible_candidates(candidate_mapping: dict, auto_threshold: float):
    eligible = {}
    for field, candidates in candidate_mapping.items():
        if not candidates:
            eligible[field] = []
            continue
        strong = [c for c in candidates if c["score"] >= max(auto_threshold, EXACT_ALIAS_THRESHOLD)]
        if strong:
            eligible[field] = strong
            continue
        best = candidates[0]
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        eligible[field] = [best] if best["score"] >= auto_threshold and best["score"] - second_score >= 0.10 else []
    return eligible


def _maximum_weight_matching(eligible: dict):
    """Find an exact maximum-weight one-to-one field/column assignment."""
    fields = [field for field, candidates in eligible.items() if candidates]
    columns = sorted({c["column"] for candidates in eligible.values() for c in candidates})
    if not fields or not columns:
        return {}

    dummy_count = len(fields)
    matrix_columns = columns + [f"__unmatched_{i}" for i in range(dummy_count)]
    column_index = {column: index for index, column in enumerate(matrix_columns)}
    n, m = len(fields), len(matrix_columns)
    inf = 10**9
    costs = [[0.0] * (m + 1) for _ in range(n + 1)]
    score_lookup = {}

    for row, field in enumerate(fields, start=1):
        by_column = {c["column"]: c["score"] for c in eligible[field]}
        for column, index in column_index.items():
            col = index + 1
            if column.startswith("__unmatched_"):
                costs[row][col] = 0.0
            elif column not in by_column:
                costs[row][col] = inf
            else:
                score = by_column[column]
                costs[row][col] = -(score + FIELD_PRIORITY.get(field, 0) * 1e-7)
                score_lookup[(field, column)] = score

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
        # score_lookup is keyed by (field, column), not by column alone.
        if (field, column) in score_lookup:
            assignment[field] = column
    return assignment


def resolve_mapping(candidate_mapping: dict, auto_threshold: float = DEFAULT_AUTO_THRESHOLD):
    """Resolve a globally optimal one-to-one automatic datasource mapping."""
    if not 0.0 <= auto_threshold <= 1.0:
        raise ValueError("auto_threshold must be between 0 and 1")

    eligible = _eligible_candidates(candidate_mapping, auto_threshold)
    assignment = _maximum_weight_matching(eligible)
    resolved = {}
    used_columns = set(assignment.values())
    for field, column in assignment.items():
        candidate = next(c for c in eligible[field] if c["column"] == column)
        resolved[field] = {"column": column, "confidence": candidate["score"]}

    needs_confirmation = {}
    for field, candidates in candidate_mapping.items():
        if field in resolved:
            continue
        available = [c for c in candidates if c["column"] not in used_columns]
        if available:
            needs_confirmation[field] = available

    return {"resolved": resolved, "needs_confirmation": needs_confirmation}
