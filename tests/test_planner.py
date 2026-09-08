import pytest

from app.planner.service import (
    QueryPlanner,
)


@pytest.mark.asyncio
async def test_simple_product_query():

    planner = QueryPlanner()

    result = await planner.plan(
        "Nike shoes"
    )

    assert (
        result.intent.value
        == "product_search"
    )


@pytest.mark.asyncio
async def test_knowledge_query():

    planner = QueryPlanner()

    result = await planner.plan(
        "What is your return policy?"
    )

    assert (
        result.intent.value
        == "knowledge_search"
    )
