CRITICAL_FIELDS = {
    "id",
    "name",
}


def should_auto_accept(
    candidates,
    field: str,
) -> bool:

    if not candidates:
        return False

    best = candidates[0]

    if field in CRITICAL_FIELDS:

        return (
            best.confidence >= 0.95
            and (
                len(candidates) == 1
                or best.confidence
                > candidates[1].confidence
            )
        )

    return best.confidence >= 0.90
