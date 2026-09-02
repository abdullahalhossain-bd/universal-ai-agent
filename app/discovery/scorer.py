from rapidfuzz.fuzz import ratio

from app.discovery.text import normalize_name
from app.discovery.vocabulary import FIELD_SYNONYMS


def score_column(
    column_name: str,
    field: str,
) -> float:

    normalized = normalize_name(column_name)

    candidates = {
        normalize_name(x)
        for x in FIELD_SYNONYMS[field]
    }

    if normalized in candidates:
        return 1.0

    return 0.0


def fuzzy_score(
    column_name: str,
    field: str,
) -> float:

    name = normalize_name(column_name)

    scores = []

    for candidate in FIELD_SYNONYMS[field]:

        candidate = normalize_name(candidate)

        scores.append(
            ratio(name, candidate) / 100
        )

    return max(scores, default=0.0)


def name_score(
    column_name: str,
    field: str,
) -> float:

    exact = score_column(column_name, field)

    if exact >= 1.0:
        return 1.0

    return fuzzy_score(column_name, field)
