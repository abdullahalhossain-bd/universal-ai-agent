from typing import Any

from app.discovery.vocabulary import FIELD_SYNONYMS
from app.discovery.text import normalize_name
from app.discovery.scorer import name_score as compute_name_score, fuzzy_score
from app.discovery.type_score import type_score as compute_type_score
from app.discovery.samples import sample_score as compute_sample_score
from app.discovery.combine import combined_score, confidence_status


def score_field_candidates(
    field: str,
    columns: list[dict[str, Any]],
    sample_data: dict[str, list] | None = None,
) -> list[dict[str, Any]]:
    """
    columns: [{"name": "selling_price", "type": "decimal"}, ...]
    sample_data: {"selling_price": [1299, 599, 2499], ...}
    """

    sample_data = sample_data or {}

    results = []

    for column in columns:

        col_name = column["name"]
        col_type = column.get("type")

        n_score = compute_name_score(col_name, field)
        t_score = compute_type_score(col_type, field)
        s_score = compute_sample_score(
            sample_data.get(col_name, []),
            field,
        )

        final_score = combined_score(n_score, t_score, s_score)

        results.append({
            "column": col_name,
            "confidence": final_score,
            "status": confidence_status(final_score),
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)

    return results


def discover_field_mapping(
    columns: list[dict[str, Any]],
    sample_data: dict[str, list] | None = None,
) -> dict[str, Any]:

    mapping = {}

    for field in FIELD_SYNONYMS.keys():

        candidates = score_field_candidates(
            field,
            columns,
            sample_data,
        )

        if not candidates:
            continue

        best = candidates[0]

        mapping[field] = {
            "column": best["column"],
            "confidence": best["confidence"],
            "status": best["status"],
            "candidates": candidates[:3],
        }

    return mapping


def score_table_as_product_resource(
    columns: list[dict[str, Any]],
    sample_data: dict[str, list] | None = None,
) -> float:
    """
    Strong signal fields for a product table: name, price, stock, sku, image_url.
    id alone is never sufficient.
    """

    strong_fields = ["name", "price", "stock", "sku", "image_url"]

    mapping = discover_field_mapping(columns, sample_data)

    found = [
        f for f in strong_fields
        if f in mapping and mapping[f]["confidence"] >= 0.70
    ]

    return round(len(found) / len(strong_fields), 4)


def detect_field(
    column_name: str,
    field: str,
) -> float:

    normalized = normalize_name(column_name)

    candidates = [
        normalize_name(x)
        for x in FIELD_SYNONYMS[field]
    ]

    if normalized in candidates:
        return 1.0

    return fuzzy_score(column_name, field)


def detect_fields(columns: list[dict]):

    result = {}

    for field in FIELD_SYNONYMS:

        candidates = []

        for column in columns:

            score = detect_field(column["name"], field)

            if score >= 0.55:

                candidates.append({
                    "column": column["name"],
                    "score": score,
                    "type": column.get("type"),
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        result[field] = candidates[:5]

    return result
