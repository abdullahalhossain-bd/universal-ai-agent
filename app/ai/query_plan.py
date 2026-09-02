from enum import Enum

from pydantic import BaseModel


class ActionType(str, Enum):

    PRODUCT_SEARCH = "product_search"
    PRODUCT_LOOKUP = "product_lookup"
    STOCK_CHECK = "stock_check"
    KNOWLEDGE_SEARCH = "knowledge_search"


class QueryAction(BaseModel):

    action: ActionType

    parameters: dict = {}


class QueryPlan(BaseModel):

    actions: list[QueryAction]
