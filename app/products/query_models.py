from pydantic import BaseModel, Field


class ProductSearchRequest(BaseModel):

    query: str | None = None

    product_name: str | None = None

    brand: str | None = None

    category: str | None = None

    min_price: float | None = None

    max_price: float | None = None

    in_stock_only: bool = False

    sku: str | None = None

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )
