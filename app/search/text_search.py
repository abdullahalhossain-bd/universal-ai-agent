from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Product


def search_products(
    db: Session,
    store_id: str,
    search_terms: list[str],
    max_price: float | None = None,
    min_price: float | None = None,
    in_stock: bool | None = None,
    limit: int = 20,
):
    query = (
        db.query(Product)
        .filter(
            Product.store_id == store_id
        )
    )

    if max_price is not None:

        query = query.filter(
            Product.price <= max_price
        )

    if min_price is not None:

        query = query.filter(
            Product.price >= min_price
        )

    if in_stock is True:

        query = query.filter(
            Product.stock > 0
        )

    elif in_stock is False:

        query = query.filter(
            Product.stock <= 0
        )

    if search_terms:

        conditions = []

        for term in search_terms:

            pattern = f"%{term}%"

            conditions.append(
                or_(
                    Product.name.ilike(pattern),
                    Product.description.ilike(pattern),
                )
            )

        query = query.filter(
            or_(*conditions)
        )

    return (
        query
        .limit(min(limit, 50))
        .all()
    )
