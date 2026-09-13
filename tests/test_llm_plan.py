from app.ai.llm_plan import (
    LLMQueryPlan,
)


def test_valid_plan():

    plan = LLMQueryPlan(
        actions=[
            {
                "type": "product_search",
                "query": "Nike Air Max",
                "filters": {
                    "max_price": 5000
                }
            }
        ]
    )

    assert len(plan.actions) == 1


def test_invalid_action():

    try:

        LLMQueryPlan(
            actions=[
                {
                    "type": "delete_database"
                }
            ]
        )

        assert False

    except Exception:

        assert True
