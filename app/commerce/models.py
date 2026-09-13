from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CommerceAction(str, Enum):
    PRODUCT_LINK = "product_link"
    STOCK_CHECK = "stock_check"
    ADD_TO_CART = "cart_add"
    UPDATE_CART = "cart_update"
    CHECKOUT = "checkout"
    ORDER_STATUS = "order_status"


class CommerceActionRequest(BaseModel):
    action: CommerceAction
    product_id: str | None = Field(default=None, max_length=255)
    quantity: int | None = Field(default=None, ge=1, le=1000)
    order_id: str | None = Field(default=None, max_length=255)
    conversation_id: str | None = Field(default=None, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_inputs(self):
        product_actions = {
            CommerceAction.PRODUCT_LINK,
            CommerceAction.STOCK_CHECK,
            CommerceAction.ADD_TO_CART,
            CommerceAction.UPDATE_CART,
        }
        if self.action in product_actions and not self.product_id:
            raise ValueError("product_id is required for this commerce action")
        if self.action in {CommerceAction.ADD_TO_CART, CommerceAction.UPDATE_CART} and self.quantity is None:
            raise ValueError("quantity is required for cart actions")
        if self.action == CommerceAction.ORDER_STATUS and not self.order_id:
            raise ValueError("order_id is required for order_status")
        return self


class CommerceActionResponse(BaseModel):
    success: bool
    action: CommerceAction
    status: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
