from typing import Any
from pydantic import BaseModel, Field


class ProductSearchRequest(BaseModel):
    query: str | None = None
    product_name: str | None = None
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    color: str | None = None
    size: str | None = None
    material: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    in_stock_only: bool = False
    sku: str | None = None
    # Merchant-defined filters. Keys are semantic attribute names supplied by
    # the datasource mapping; values may be strings/numbers or comparison specs.
    attributes: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)
