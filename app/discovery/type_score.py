PRICE_TYPES = {
    "decimal",
    "numeric",
    "float",
    "double",
    "real",
    "int",
    "integer",
}


STOCK_TYPES = {
    "int",
    "integer",
    "smallint",
    "bigint",
    "decimal",
    "numeric",
}


def type_score(
    data_type: str | None,
    field: str,
) -> float:

    if not data_type:
        return 0.5

    normalized = data_type.lower().strip()

    if field == "price":
        return 1.0 if normalized in PRICE_TYPES else 0.3

    if field == "stock":
        return 1.0 if normalized in STOCK_TYPES else 0.3

    return 0.5
