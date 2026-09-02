from app.search.filters import SearchFilters
from enum import Enum
from pydantic import BaseModel, Field


class Intent(str, Enum):
    PRODUCT_SEARCH = "product_search"
    KNOWLEDGE_SEARCH = "knowledge_search"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ProductFilters(BaseModel):
    product_name: str | None = None
    brand: str | None = None
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    in_stock: bool = False


class PlannedAction(BaseModel):
    intent: Intent

    product_filters: ProductFilters | None = None

    knowledge_query: str | None = None

    confidence: float = Field(
        ge=0,
        le=1,
    )


class SearchIntent(str, Enum):

    SEARCH = "search"

    CHEAPEST = "cheapest"

    MOST_EXPENSIVE = "most_expensive"

    IN_STOCK = "in_stock"

    SIMILAR = "similar"


class QueryPlan(BaseModel):

    use_product_search: bool = False

    use_knowledge_search: bool = False

    product_filters: SearchFilters | None = None

    search_query: str | None = None

    intent: str = "unknown"

    confidence: float = 0.0

