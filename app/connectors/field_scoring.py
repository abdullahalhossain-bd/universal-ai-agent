FIELD_NAME_HINTS = {

    "id": [
        "id",
        "product_id",
        "item_id",
        "uid",
        "uuid",
    ],

    "name": [
        "name",
        "title",
        "product_name",
        "item_name",
    ],

    "price": [
        "price",
        "selling_price",
        "sale_price",
        "amount",
    ],

    "stock": [
        "stock",
        "qty",
        "quantity",
        "inventory",
        "available",
        "qty_available",
    ],

    "image_url": [
        "image",
        "photo",
        "thumbnail",
        "picture",
        "featured_image",
        "image_url",
    ],
}


def normalize(text: str):

    return (
        text.lower()
        .strip()
        .replace("-", "_")
        .replace(" ", "_")
    )


def score_column(
    field: str,
    column_name: str,
    column_type: str | None = None,
    sample_values: list | None = None,
):

    score = 0.0

    hints = FIELD_NAME_HINTS.get(field, [])

    normalized_column = normalize(column_name)

    if normalized_column in [
        normalize(h) for h in hints
    ]:
        score += 0.6

    elif any(
        normalize(h) in normalized_column
        for h in hints
    ):
        score += 0.3

    if field == "price" and column_type in (
        "decimal",
        "float",
        "numeric",
    ):
        score += 0.2

    if field == "stock" and column_type in (
        "int",
        "integer",
        "bigint",
    ):
        score += 0.2

    if sample_values:

        non_null = [
            v for v in sample_values
            if v is not None
        ]

        if non_null:
            score += 0.1

    return min(score, 1.0)
