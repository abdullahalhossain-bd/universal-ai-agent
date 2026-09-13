from app.discovery.samples import looks_like_image


def analyze_column_values(values: list) -> dict:

    if not values:

        return {
            "count": 0,
            "numeric_ratio": 0,
            "null_ratio": 1,
        }

    null_count = sum(value is None for value in values)

    numeric_count = 0

    for value in values:

        if value is None:
            continue

        try:
            float(value)
            numeric_count += 1

        except (TypeError, ValueError):
            pass

    return {
        "count": len(values),
        "numeric_ratio": numeric_count / len(values),
        "null_ratio": null_count / len(values),
    }


def non_negative_ratio(values: list) -> float:

    valid = [v for v in values if v is not None]

    if not valid:
        return 0.0

    good = 0

    for value in valid:

        try:

            if float(value) >= 0:
                good += 1

        except (TypeError, ValueError):
            pass

    return good / len(valid)


def image_ratio(values: list) -> float:

    if not values:
        return 0.0

    matches = sum(looks_like_image(v) for v in values)

    return matches / len(values)
