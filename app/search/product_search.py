from app.search.base import (
    SearchProvider,
)


class ProductSearchProvider(
    SearchProvider
):

    def __init__(
        self,
        product_service,
    ):

        self.product_service = (
            product_service
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
    ):

        request = self._build_request(
            query,
            limit,
        )

        products = (
            await self.product_service.search(
                request
            )
        )

        return products

    def _build_request(
        self,
        query,
        limit,
    ):
        # Temporary:
        # Query planner will populate
        # structured filters later.

        from app.products.query_models import (
            ProductSearchRequest,
        )

        return ProductSearchRequest(
            product_name=query,
            limit=limit,
        )
