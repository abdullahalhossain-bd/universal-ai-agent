from app.search.base import SearchProvider
from app.products.query_models import ProductSearchRequest


class ProductSearchProvider(SearchProvider):
    """DB-backed product search adapter with legacy API compatibility."""

    def __init__(self, product_service):
        self.product_service = product_service

    async def search(self, query, limit: int = 10):
        request = self._build_request(query, limit)
        return await self.product_service.search(request)

    def _build_request(self, query, limit):
        if isinstance(query, ProductSearchRequest):
            # Preserve an explicitly supplied structured request while
            # respecting the provider's public limit argument.
            return query.model_copy(update={"limit": limit})

        if hasattr(query, "model_dump"):
            data = query.model_dump()
            return ProductSearchRequest(**data, limit=limit)

        if isinstance(query, dict):
            data = dict(query)
            data["limit"] = limit
            return ProductSearchRequest(**data)

        return ProductSearchRequest(
            query=str(query) if query is not None else None,
            product_name=str(query) if query is not None else None,
            limit=limit,
        )
