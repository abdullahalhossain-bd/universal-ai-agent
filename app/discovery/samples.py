def numeric_ratio(values: list) -> float:

    if not values:
        return 0.0

    numeric = 0

    for value in values:

        try:
            float(value)
            numeric += 1

        except (TypeError, ValueError):
            pass

    return numeric / len(values)


def looks_like_image(value) -> bool:

    if not isinstance(value, str):
        return False

    value = value.lower()

    extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".avif",
    )

    return (
        value.startswith("http://")
        or value.startswith("https://")
    ) and value.endswith(extensions)


def image_ratio(values: list) -> float:

    if not values:
        return 0.0

    matches = sum(
        1 for v in values if looks_like_image(v)
    )

    return matches / len(values)


def sample_score(
    values: list,
    field: str,
) -> float:

    if field in ("price", "stock"):
        return numeric_ratio(values)

    if field == "image_url":
        return image_ratio(values)

    return 0.5
