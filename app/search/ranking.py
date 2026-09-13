import re


def calculate_score(
    product,
    search_terms: list[str],
) -> float:

    name = (
        getattr(product, "name", None)
        or ""
    ).lower()

    description = (
        getattr(product, "description", None)
        or ""
    ).lower()

    brand = (
        getattr(product, "brand", None)
        or ""
    ).lower()

    category = (
        getattr(product, "category", None)
        or ""
    ).lower()

    sku = (
        getattr(product, "sku", None)
        or ""
    ).lower()

    name_words = set(
        re.findall(
            r"\w+",
            name,
            flags=re.UNICODE,
        )
    )

    score = 0.0

    for term in search_terms:

        term = term.lower().strip()

        if not term:
            continue

        if term in name_words:
            score += 50

        elif term in name:
            score += 30

        if term in brand:
            score += 20

        if term in category:
            score += 20

        if term in description:
            score += 10

        if term in sku:
            score += 10

    return score


def search_and_rank(
    db,
    store_id,
    search_terms,
    max_price=None,
    min_price=None,
    in_stock=None,
    limit=20,
    candidate_pool_size=None,
):
    from app.search.text_search import (
        search_products,
    )

    if candidate_pool_size is None:
        candidate_pool_size = max(
            limit * 5,
            100,
        )

    products = search_products(
        db=db,
        store_id=store_id,
        search_terms=search_terms,
        max_price=max_price,
        min_price=min_price,
        in_stock=in_stock,
        limit=candidate_pool_size,
    )

    ranked = []

    for product in products:

        score = calculate_score(
            product,
            search_terms,
        )

        ranked.append(
            (
                score,
                product,
            )
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        product
        for _, product in ranked[:limit]
    ]