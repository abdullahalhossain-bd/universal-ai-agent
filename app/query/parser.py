from app.query.models import (
    QueryIntent,
    QueryFilters,
)

from app.query.rules import (
    detect_intent,
    extract_max_price,
    wants_in_stock,
    extract_color,
    extract_search_terms,
)


def parse_query(text: str) -> QueryIntent:
    intent = detect_intent(text)
    max_price = extract_max_price(text)
    in_stock = wants_in_stock(text)
    color = extract_color(text)
    search_terms = extract_search_terms(text)

    if in_stock is not None and (search_terms or intent == "stock_check"):
        intent = "product_search"

    filters = QueryFilters(
        max_price=max_price,
        in_stock=in_stock,
        color=color,
    )

    return QueryIntent(
        intent=intent,
        query=text,
        search_terms=search_terms,
        filters=filters,
    )
