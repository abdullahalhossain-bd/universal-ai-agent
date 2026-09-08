from enum import Enum


class Intent(str, Enum):

    PRODUCT_SEARCH = "product_search"
    PRODUCT_DETAIL = "product_detail"
    PRICE = "price"
    STOCK = "stock"
    WEBSITE_QA = "website_qa"
    RECOMMENDATION = "recommendation"
    IMAGE_SEARCH = "image_search"
    ORDER = "order"
    UNKNOWN = "unknown"
