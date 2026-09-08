from app.search.base import SearchProvider
from app.products.query_models import ProductSearchRequest


class ProductSearchProvider(SearchProvider):
    def __init__(self, product_service):
        self.product_service = product_service

    async def search(self, query, limit: int = 10):
        request = self._build_request(query, limit)
        return await self.product_service.search(request)

    def _build_request(self, query, limit):
        """Convert planner output to a tolerant structured product query."""
        if isinstance(query, ProductSearchRequest):
            return query.model_copy(update={"limit": limit})

        if hasattr(query, "model_dump"):
            data = query.model_dump()
            natural_text = data.get("query") or data.get("product_name")
            return ProductSearchRequest(
                query=natural_text or None,
                product_name=None,
                brand=data.get("brand"),
                category=data.get("category"),
                min_price=data.get("min_price"),
                max_price=data.get("max_price"),
                in_stock_only=bool(data.get("in_stock", data.get("in_stock_only", False))),
                sku=data.get("sku"),
                limit=min(limit, int(data.get("limit", limit) or limit)),
            )

        text = str(query or "").strip()
        return ProductSearchRequest(query=text or None, limit=limit)
