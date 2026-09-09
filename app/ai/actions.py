from enum import Enum


class AllowedAction(str, Enum):
    PRODUCT_SEARCH = "product_search"
    PRODUCT_LOOKUP = "product_lookup"
    STOCK_CHECK = "stock_check"
    KNOWLEDGE_SEARCH = "knowledge_search"

    # Commerce actions are explicit capabilities. Mutating actions must still
    # be backed by a merchant adapter before they can execute.
    PRODUCT_LINK = "product_link"
    CART_ADD = "cart_add"
    CART_UPDATE = "cart_update"
    CHECKOUT = "checkout"
    ORDER_STATUS = "order_status"
