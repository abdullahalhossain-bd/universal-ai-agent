"""
Pydantic models for search filters.

Used by the planner subsystem (`app.planner.models.QueryPlan`) to express
a unified set of product-search filters that downstream search services
can consume.
"""

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    """Unified product-search filter bag."""

    query: str | None = None

    product_name: str | None = None

    brand: str | None = None
    category: str | None = None
    sku: str | None = None

    min_price: float | None = None
    max_price: float | None = None

    in_stock: bool = False

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
    )
