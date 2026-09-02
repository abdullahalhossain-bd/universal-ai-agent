from app.discovery.text import normalize_name


PRODUCT_TABLE_NAMES = {
    "product",
    "products",
    "item",
    "items",
    "catalog",
    "catalogue",
    "inventory",
}


PRODUCT_SIGNALS = {
    "name",
    "title",
    "price",
    "stock",
    "sku",
    "description",
    "image",
}


def detect_table(
    table_name: str,
    columns: list[dict],
) -> float:

    table_score = 0.0

    normalized_table = normalize_name(table_name)

    if normalized_table in PRODUCT_TABLE_NAMES:
        table_score += 0.40

    normalized_columns = {
        normalize_name(column["name"])
        for column in columns
    }

    matches = normalized_columns & PRODUCT_SIGNALS

    signal_score = min(len(matches) / 5, 1.0)

    table_score += signal_score * 0.60

    return round(min(table_score, 1.0), 4)
