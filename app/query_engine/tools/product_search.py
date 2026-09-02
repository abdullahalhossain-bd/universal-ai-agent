"""
Product search tool for the (currently unwired) query_engine plan
executor. See app/ARCHITECTURE_CLEANUP.md item 3: this deliberately
mirrors `ChatService._search_products` in app/chat/service.py — same
store-scoping, same synonym expansion — rather than inventing a
second search implementation. If the two ever need to diverge,
extract a shared helper instead of copy-drifting.

Requires a DB session bound via `bind_db()` before `execute()` is
called — see `StockTool` in app/query_engine/tools/stock_tool.py for
the same pattern. `PlanExecutor.run()` binds it automatically.
"""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.query_engine.tools.base import BaseTool
from app.db.models import Product
from app.search.synonyms import expand_terms


class ProductSearchTool(BaseTool):

    name = "product_search"
    description = "Search products by filters (color, price, category, brand)"

    def __init__(self, db: Session | None = None):
        self._db = db

    def bind_db(self, db: Session) -> "ProductSearchTool":
        self._db = db
        return self

    async def execute(
        self,
        tenant_id: str,
        filters: dict | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ):
        if self._db is None:
            return {
                "error": (
                    "ProductSearchTool requires a database "
                    "session (bind_db)."
                )
            }

        filters = filters or {}

        db_query = self._db.query(Product).filter(
            Product.store_id == tenant_id
        )

        min_price = filters.get("min_price")
        if min_price is not None:
            db_query = db_query.filter(Product.price >= min_price)

        max_price = filters.get("max_price")
        if max_price is not None:
            db_query = db_query.filter(Product.price <= max_price)

        if filters.get("in_stock"):
            db_query = db_query.filter(Product.stock > 0)

        # Free-text terms: an explicit `query`, falling back to the
        # `color` entity extracted by app.query_engine.entities (the
        # only free-text-ish filter the current planner produces).
        # Both go through the same synonym expansion as the live
        # chat path so "কালো" and "black" match the same rows.
        search_terms = []

        if query:
            search_terms.extend(query.split())
        elif filters.get("color"):
            search_terms.append(filters["color"])

        group_conditions = []

        for term in search_terms:
            cleaned = term.strip(".,!?;:()[]{}\"'")

            if not cleaned or len(cleaned) < 2:
                continue

            synonyms = expand_terms([cleaned])

            if not synonyms:
                continue

            group_conditions.append(
                or_(
                    *[
                        Product.name.ilike(f"%{synonym}%")
                        for synonym in synonyms
                    ]
                )
            )

        if group_conditions:
            db_query = db_query.filter(and_(*group_conditions))

        products = (
            db_query.order_by(Product.name.asc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": (
                    float(product.price)
                    if product.price is not None
                    else None
                ),
                "stock": (
                    float(product.stock)
                    if product.stock is not None
                    else None
                ),
                "image_url": product.image_url,
                "product_url": product.product_url,
            }
            for product in products
        ]
