from app.ai.rule_router import (
    RuleIntentRouter,
)

from app.ai.intent_models import (
    IntentType,
)


def test_product_query():

    router = RuleIntentRouter()

    result = router.route(
        "Nike product price"
    )

    assert (
        IntentType.PRODUCT_SEARCH
        in result.intents
    )


def test_shipping_query():

    router = RuleIntentRouter()

    result = router.route(
        "How long is delivery?"
    )

    assert (
        IntentType.WEBSITE_KNOWLEDGE
        in result.intents
    )


def test_stock_query():

    router = RuleIntentRouter()

    result = router.route(
        "Is Nike Air Max available?"
    )

    assert (
        IntentType.STOCK_CHECK
        in result.intents
    )
