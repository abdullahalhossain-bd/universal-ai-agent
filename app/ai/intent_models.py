from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):

    PRODUCT_SEARCH = "product_search"
    PRODUCT_LOOKUP = "product_lookup"
    STOCK_CHECK = "stock_check"
    WEBSITE_KNOWLEDGE = "website_knowledge"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class QueryFilters(BaseModel):

    product_name: str | None = None
    brand: str | None = None
    category: str | None = None

    min_price: float | None = None
    max_price: float | None = None

    in_stock_only: bool = False


class IntentResult(BaseModel):

    intents: list[IntentType]

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )

    confidence: float = 0.0
