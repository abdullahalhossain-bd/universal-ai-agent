from typing import Literal

from pydantic import BaseModel, Field


class ProductSearchRequest(BaseModel):
    query: str | None = None
    category: str | None = None
    brand: str | None = None

    min_price: float | None = None
    max_price: float | None = None

    in_stock_only: bool = False

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )


class ProductSearchResult(BaseModel):
    products: list[dict] = Field(
        default_factory=list
    )
    total: int = 0


class StockResult(BaseModel):
    product_id: str
    stock: int | None
    available: bool
