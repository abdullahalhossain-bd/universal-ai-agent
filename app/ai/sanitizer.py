class QuerySanitizer:

    MAX_QUERY_LENGTH = 300

    def clean(
        self,
        query: str | None,
    ) -> str | None:

        if not query:
            return None

        query = " ".join(
            query.split()
        )

        return query[
            :self.MAX_QUERY_LENGTH
        ]

    def clean_filters(
        self,
        filters: dict,
    ) -> dict:

        allowed = {
            "brand",
            "category",
            "min_price",
            "max_price",
            "in_stock_only",
            "product_name",
            "sku",
        }

        return {
            key: value
            for key, value in filters.items()
            if key in allowed
        }
