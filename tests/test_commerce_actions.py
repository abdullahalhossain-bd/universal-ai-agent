import asyncio

import pytest
from pydantic import ValidationError

from app.commerce.models import CommerceAction, CommerceActionRequest
from app.commerce.service import CommerceActionService


@pytest.mark.parametrize(
    "payload",
    [
        {"action": CommerceAction.PRODUCT_LINK},
        {"action": CommerceAction.STOCK_CHECK},
        {"action": CommerceAction.CART_ADD, "product_id": "p1"},
        {"action": CommerceAction.CART_UPDATE, "product_id": "p1"},
        {"action": CommerceAction.ORDER_STATUS},
    ],
)
def test_action_contract_rejects_missing_required_inputs(payload):
    with pytest.raises(ValidationError):
        CommerceActionRequest(**payload)


def test_mutating_action_is_never_executed_without_merchant_adapter():
    request = CommerceActionRequest(
        action=CommerceAction.CART_ADD,
        product_id="missing",
        quantity=1,
    )
    # Adapter validation happens before any database lookup or external call.
    response = asyncio.run(CommerceActionService(db=None).execute("store-1", request))
    assert response.success is False
    assert response.status == "not_configured"
