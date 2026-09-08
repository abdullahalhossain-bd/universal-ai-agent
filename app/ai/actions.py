from enum import Enum


class AllowedAction(str, Enum):

    PRODUCT_SEARCH = "product_search"
    PRODUCT_LOOKUP = "product_lookup"
    STOCK_CHECK = "stock_check"
    KNOWLEDGE_SEARCH = "knowledge_search"
