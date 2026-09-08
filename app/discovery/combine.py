def combined_score(
    name_score: float,
    type_score: float,
    sample_score: float,
) -> float:

    score = (
        name_score * 0.55
        + type_score * 0.20
        + sample_score * 0.25
    )

    return round(
        min(score, 1.0),
        4,
    )


def confidence_status(score: float) -> str:

    if score >= 0.90:
        return "auto"

    if score >= 0.70:
        return "review"

    return "unknown"
