from __future__ import annotations

from typing import Any, Protocol

from app.commerce.models import CommerceAction, CommerceActionRequest, CommerceActionResponse
from app.db.models import Product


class MerchantCommerceAdapter(Protocol):
    """Optional merchant-side adapter for real cart/checkout/order APIs.

    Implementations are registered by the integration layer. The core service
    never guesses an endpoint or mutates a merchant system without an adapter.
    """

    async def execute(self, action: CommerceAction, payload: dict[str, Any]) -> dict[str, Any]: ...


class CommerceActionService:
    """Tenant-safe commerce action dispatcher.

    Read-only product link/stock actions are handled locally from the verified
    catalog. Mutating actions require an explicit merchant adapter, preventing
    accidental writes to an unknown REST API.
    """

    _MUTATING = {
        CommerceAction.ADD_TO_CART,
        CommerceAction.UPDATE_CART,
        CommerceAction.CHECKOUT,
        CommerceAction.ORDER_STATUS,
    }

    def __init__(self, db, adapter: MerchantCommerceAdapter | None = None):
        self.db = db
        self.adapter = adapter

    def _product(self, store_id: str, product_id: str) -> Product | None:
        return (
            self.db.query(Product)
            .filter(Product.store_id == store_id, Product.id == product_id)
            .first()
        )

    async def execute(self, store_id: str, request: CommerceActionRequest) -> CommerceActionResponse:
        if request.action in self._MUTATING and self.adapter is None:
            return CommerceActionResponse(
                success=False,
                action=request.action,
                status="not_configured",
                message="This store has not configured a commerce action integration yet.",
            )

        product = None
        if request.product_id:
            product = self._product(store_id, request.product_id)
            if product is None:
                return CommerceActionResponse(
                    success=False,
                    action=request.action,
                    status="not_found",
                    message="The requested product was not found in this store's catalog.",
                )

        if request.action == CommerceAction.PRODUCT_LINK:
            if not product.product_url:
                return CommerceActionResponse(
                    success=False,
                    action=request.action,
                    status="unavailable",
                    message="This product does not have a product URL in the catalog.",
                )
            return CommerceActionResponse(
                success=True,
                action=request.action,
                status="ok",
                message="Product link retrieved.",
                data={"product_id": product.id, "url": product.product_url},
            )

        if request.action == CommerceAction.STOCK_CHECK:
            stock = product.stock
            return CommerceActionResponse(
                success=stock is not None,
                action=request.action,
                status="ok" if stock is not None else "unknown",
                message="Current catalog stock retrieved." if stock is not None else "Stock is not tracked for this product.",
                data={"product_id": product.id, "stock": float(stock) if stock is not None else None},
            )

        payload = request.model_dump(exclude_none=True)
        payload["store_id"] = store_id
        if product is not None:
            payload["verified_product"] = {
                "id": product.id,
                "name": product.name,
                "price": float(product.price) if product.price is not None else None,
                "stock": float(product.stock) if product.stock is not None else None,
            }

        result = await self.adapter.execute(request.action, payload)
        if not isinstance(result, dict):
            result = {"result": result}

        return CommerceActionResponse(
            success=True,
            action=request.action,
            status="ok",
            message="Commerce action completed.",
            data=result,
        )
