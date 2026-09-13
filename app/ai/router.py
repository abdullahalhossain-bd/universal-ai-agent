"""
LLM routing and complexity classification.
"""

from enum import Enum

from app.ai.cost_engine import (
    estimate_max_cost,
    estimate_messages_tokens,
)


class QueryComplexity(str, Enum):

    ZERO = "zero"

    LOW = "low"

    MEDIUM = "medium"

    HIGH = "high"


# ---------------------------------
# Query complexity
# ---------------------------------

def classify_query(
    message: str,
    intent: str,
) -> QueryComplexity:

    text = (
        message
        or ""
    ).lower().strip()

    if intent in {
        "price",
        "stock",
        "product_lookup",
    }:

        return QueryComplexity.ZERO

    if intent in {
        "simple_faq",
        "delivery",
        "return_policy",
    }:

        return QueryComplexity.LOW

    if len(text) < 200:

        return QueryComplexity.MEDIUM

    return QueryComplexity.HIGH


# ---------------------------------
# Logical route
# ---------------------------------

def choose_route(
    complexity: QueryComplexity,
    plan: str = "free",
) -> str:

    if complexity == QueryComplexity.ZERO:

        return "NO_LLM"

    if complexity == QueryComplexity.LOW:

        return "CHEAP_LLM"

    if complexity == QueryComplexity.MEDIUM:

        return "BALANCED_LLM"

    if (
        complexity == QueryComplexity.HIGH
        and plan == "premium"
    ):

        return "STRONG_LLM"

    return "BALANCED_LLM"


# ---------------------------------
# Provider interface
# ---------------------------------

class ModelProvider:

    async def generate(
        self,
        messages,
        max_tokens=500,
    ):

        raise NotImplementedError


# ---------------------------------
# Provider/model route mapping
# ---------------------------------

def route_for_complexity(
    complexity: QueryComplexity,
    plan_name: str = "free",
) -> list[str]:
    """
    Return ordered provider/model names.

    Currently only Groq is active.
    """

    if complexity == QueryComplexity.ZERO:

        return []

    if complexity == QueryComplexity.LOW:

        return [
            "groq",
        ]

    if complexity == QueryComplexity.MEDIUM:

        return [
            "groq",
        ]

    if (
        complexity == QueryComplexity.HIGH
        and plan_name == "premium"
    ):

        return [
            "groq",
        ]

    return [
        "groq",
    ]


# ---------------------------------
# Cost map
# ---------------------------------

DEFAULT_MODEL_PRICING = {
    "groq": {
        "input": 0.075,
        "output": 0.30,
    },
}


# ---------------------------------
# Build estimated costs
# ---------------------------------

def build_estimated_costs(
    messages: list[dict],
    max_output_tokens: int = 500,
    model_pricing: dict | None = None,
) -> dict:
    """
    Estimate maximum cost per candidate model.
    """

    pricing = (
        model_pricing
        or DEFAULT_MODEL_PRICING
    )

    input_tokens = (
        estimate_messages_tokens(
            messages
        )
    )

    estimated_costs = {}

    for model, prices in (
        pricing.items()
    ):

        estimated_costs[model] = (
            estimate_max_cost(
                input_tokens=input_tokens,
                max_output_tokens=max_output_tokens,
                input_price=prices[
                    "input"
                ],
                output_price=prices[
                    "output"
                ],
            )
        )

    return estimated_costs


# ---------------------------------
# Select affordable model
# ---------------------------------

async def select_model(
    store,
    complexity: QueryComplexity,
    estimated_costs: dict,
    cost_engine,
    route_for_complexity_func=route_for_complexity,
):
    """
    Select the first affordable route.

    Returns:
        provider/model name
        or "NO_LLM"
    """

    plan_name = getattr(
        store,
        "plan",
        "free",
    )

    preferred = (
        route_for_complexity_func(
            complexity,
            plan_name,
        )
    )

    if not preferred:

        return "NO_LLM"

    if isinstance(
        preferred,
        str,
    ):

        preferred = [
            preferred
        ]

    for model in preferred:

        estimated_cost = (
            float(
                estimated_costs.get(
                    model,
                    0.0,
                )
            )
        )

        allowed = (
            cost_engine.can_use_model(
                store=store,
                model=model,
                estimated_cost=estimated_cost,
            )
        )

        if allowed:

            return model

    return "NO_LLM"