PRODUCT_TABLE_WORDS = {
    "product",
    "products",
    "item",
    "items",
    "catalog",
    "inventory",
}


def score_table(
    table_name,
    columns,
):

    score = 0

    table = table_name.lower()

    if table in PRODUCT_TABLE_WORDS:
        score += 30

    column_text = " ".join(
        c.lower()
        for c in columns
    )

    if "price" in column_text:
        score += 20

    if (
        "stock" in column_text
        or "quantity" in column_text
        or "qty" in column_text
    ):
        score += 20

    if (
        "name" in column_text
        or "title" in column_text
    ):
        score += 10

    if (
        "image" in column_text
        or "image_url" in column_text
    ):
        score += 10

    if "sku" in column_text:
        score += 10

    return score
