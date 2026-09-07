class QuerySanitizer:
    MAX_QUERY_LENGTH = 300

    def clean(self, query: str | None) -> str | None:
        if not query:
            return None
        query = " ".join(query.split())
        return query[:self.MAX_QUERY_LENGTH]

    def clean_filters(self, filters: dict) -> dict:
        if not isinstance(filters, dict):
            return {}

        allowed = {
            "query",
            "brand",
            "category",
            "min_price",
            "max_price",
            "in_stock",
            "in_stock_only",
            "product_name",
            "sku",
            "model",
            "attributes",
            "limit",
        }

        cleaned = {
            key: value for key, value in filters.items() if key in allowed
        }

        # Prevent malformed LLM values from reaching SQL construction.
        for key in ("min_price", "max_price"):
            if key in cleaned:
                try:
                    cleaned[key] = float(cleaned[key])
                except (TypeError, ValueError):
                    cleaned.pop(key, None)

        for key in ("in_stock", "in_stock_only"):
            if key in cleaned and not isinstance(cleaned[key], bool):
                cleaned[key] = str(cleaned[key]).lower() in {"1", "true", "yes"}

        if "limit" in cleaned:
            try:
                cleaned["limit"] = max(1, min(50, int(cleaned["limit"])))
            except (TypeError, ValueError):
                cleaned.pop("limit", None)

        if "attributes" in cleaned and not isinstance(cleaned["attributes"], dict):
            cleaned.pop("attributes", None)

        return cleaned
