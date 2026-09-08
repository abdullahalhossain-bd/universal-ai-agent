from app.services.query_engine import QueryEngine
from app.services.query_models import (
    ProductSearchRequest,
)


class ProductQueryService:

    def __init__(
        self,
        database_url: str,
        mapping: dict[str, str],
        product_table: str,
    ):
        self.engine = QueryEngine(
            database_url=database_url,
            mapping=mapping,
            product_table=product_table,
        )

    def search(
        self,
        query: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock_only: bool = False,
        limit: int = 5,
    ):

        request = ProductSearchRequest(
            query=query,
            brand=brand,
            category=category,
            min_price=min_price,
            max_price=max_price,
            in_stock_only=in_stock_only,
            limit=limit,
        )

        return self.engine.search_products(
            request
        )
