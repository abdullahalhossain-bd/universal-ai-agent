from pydantic import BaseModel, Field


class ProductSearchRequest(BaseModel):

    # Free-text query. Kept separate from product_name for API compatibility;
    # callers may still use product_name as the legacy search input.
    query: str | None = None

    product_name: str | None = None

    brand: str | None = None

    category: str | None = None

    model: str | None = None

    attributes: dict | None = None

    min_price: float | None = None

    max_price: float | None = None

    in_stock_only: bool = False

    sku: str | None = None

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )
