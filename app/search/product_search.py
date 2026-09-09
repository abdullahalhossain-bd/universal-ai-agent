from app.search.base import SearchProvider
from app.products.query_models import ProductSearchRequest
from app.products.query_intent import extract_product_intent


class ProductSearchProvider(SearchProvider):
    def __init__(self, product_service):
        self.product_service = product_service

    async def search(self, query, limit: int = 10, **filters):
        request = self._build_request(query, limit, filters)
        return await self.product_service.search(request)

    def _build_request(self, query, limit, extra_filters=None):
        """Convert planner or natural language input into structured search."""
        extra_filters = extra_filters or {}
        attribute_mapping = getattr(self.product_service, "mapping", {}).get("attributes", {})

        if isinstance(query, ProductSearchRequest):
            data = query.model_dump(exclude_none=True)
            data.update({k: v for k, v in extra_filters.items() if v is not None})
            data["limit"] = limit
            return ProductSearchRequest(**data)

        if hasattr(query, "model_dump"):
            data = query.model_dump(exclude_none=True)
            nested = data.pop("filters", {}) or {}
            merged = {**nested, **data, **extra_filters}
            natural_text = merged.get("query") or merged.get("product_name")
            return ProductSearchRequest(
                query=natural_text or None,
                product_name=None,
                brand=merged.get("brand"),
                category=merged.get("category"),
                subcategory=merged.get("subcategory"),
                color=merged.get("color"),
                size=merged.get("size"),
                material=merged.get("material"),
                min_price=merged.get("min_price"),
                max_price=merged.get("max_price"),
                in_stock_only=bool(merged.get("in_stock", merged.get("in_stock_only", False))),
                sku=merged.get("sku"),
                attributes=merged.get("attributes") or {},
                limit=min(limit, int(merged.get("limit", limit) or limit)),
            )

        text = str(query or "").strip()
        intent = extract_product_intent(text, attribute_fields=attribute_mapping)
        intent.update({k: v for k, v in extra_filters.items() if v is not None})
        intent["limit"] = limit
        return ProductSearchRequest(**intent)
