from pydantic import BaseModel, Field


class QueryFilters(BaseModel):

    min_price: float | None = None
    max_price: float | None = None

    category: str | None = None
    brand: str | None = None
    color: str | None = None

    in_stock: bool | None = None


class QueryIntent(BaseModel):

    intent: str

    query: str | None = None

    search_terms: list[str] = Field(
        default_factory=list
    )

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )

    product_reference: str | None = None

    field: str | None = None

    order_id: str | None = None
