from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    PRODUCT_SEARCH = "product_search"
    PRODUCT_LOOKUP = "product_lookup"
    STOCK_CHECK = "stock_check"
    KNOWLEDGE_SEARCH = "knowledge_search"
    PRODUCT_LINK = "product_link"
    CART_ADD = "cart_add"
    CART_UPDATE = "cart_update"
    CHECKOUT = "checkout"
    ORDER_STATUS = "order_status"


class QueryAction(BaseModel):
    action: ActionType
    parameters: dict = Field(default_factory=dict)


class QueryPlan(BaseModel):
    actions: list[QueryAction]
