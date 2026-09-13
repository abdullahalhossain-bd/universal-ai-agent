from typing import Any

from sqlalchemy import (
    create_engine,
    text,
)

from app.services.product_mapper import (
    ProductMapper,
)
from app.services.query_models import (
    ProductSearchRequest,
)


class QueryEngine:

    def __init__(
        self,
        database_url: str,
        mapping: dict[str, str],
        product_table: str,
    ):
        self.database_url = database_url
        self.mapping = mapping
        self.product_table = product_table

    def search_products(
        self,
        request: ProductSearchRequest,
    ):

        engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
        )

        preparer = (
            engine
            .dialect
            .identifier_preparer
        )

        table = preparer.quote(
            self.product_table
        )

        conditions = []
        params: dict[str, Any] = {}

        # -----------------------
        # Search
        # -----------------------

        name_column = self.mapping.get("name")

        if request.query and name_column:

            column = preparer.quote(
                name_column
            )

            conditions.append(
                f"{column} ILIKE :search"
            )

            params["search"] = (
                f"%{request.query}%"
            )

        # -----------------------
        # Category
        # -----------------------

        category_column = (
            self.mapping.get("category")
        )

        if (
            request.category
            and category_column
        ):

            column = preparer.quote(
                category_column
            )

            conditions.append(
                f"{column} ILIKE :category"
            )

            params["category"] = (
                f"%{request.category}%"
            )

        # -----------------------
        # Brand
        # -----------------------

        brand_column = (
            self.mapping.get("brand")
        )

        if request.brand and brand_column:

            column = preparer.quote(
                brand_column
            )

            conditions.append(
                f"{column} ILIKE :brand"
            )

            params["brand"] = (
                f"%{request.brand}%"
            )

        # -----------------------
        # Price
        # -----------------------

        price_column = (
            self.mapping.get("price")
        )

        if (
            request.min_price is not None
            and price_column
        ):

            column = preparer.quote(
                price_column
            )

            conditions.append(
                f"{column} >= :min_price"
            )

            params["min_price"] = (
                request.min_price
            )

        if (
            request.max_price is not None
            and price_column
        ):

            column = preparer.quote(
                price_column
            )

            conditions.append(
                f"{column} <= :max_price"
            )

            params["max_price"] = (
                request.max_price
            )

        # -----------------------
        # Stock
        # -----------------------

        stock_column = (
            self.mapping.get("stock")
        )

        if (
            request.in_stock_only
            and stock_column
        ):

            column = preparer.quote(
                stock_column
            )

            conditions.append(
                f"{column} > 0"
            )

        # -----------------------
        # Query
        # -----------------------

        where_clause = ""

        if conditions:

            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        query = text(
            f"""
            SELECT *
            FROM {table}
            {where_clause}
            LIMIT :limit
            """
        )

        params["limit"] = request.limit

        with engine.connect() as conn:

            rows = (
                conn.execute(
                    query,
                    params,
                )
                .mappings()
                .all()
            )

        engine.dispose()

        mapper = ProductMapper()

        products = [
            mapper.map(
                dict(row),
                self.mapping,
            )
            for row in rows
        ]

        return products
