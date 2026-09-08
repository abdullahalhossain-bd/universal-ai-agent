"""
LLM cost and budget control.

Responsibilities:
- Estimate token usage before an LLM request
- Estimate request cost
- Check store monthly budget
- Report current monthly usage
"""

from __future__ import annotations


class CostEngine:

    def __init__(
        self,
        usage_repo,
    ):
        self.usage_repo = usage_repo

    # ---------------------------------
    # Monthly usage
    # ---------------------------------

    def get_monthly_usage(
        self,
        store_id: str,
    ) -> float:

        used = (
            self.usage_repo
            .get_monthly_usage(
                store_id
            )
        )

        return float(
            used or 0.0
        )

    # ---------------------------------
    # Remaining budget
    # ---------------------------------

    def remaining_budget(
        self,
        store,
    ) -> float:

        monthly_budget = float(
            getattr(
                store,
                "monthly_budget",
                0.0,
            )
        )

        used = self.get_monthly_usage(
            store.id
        )

        return max(
            monthly_budget - used,
            0.0,
        )

    # ---------------------------------
    # Budget check
    # ---------------------------------

    def can_use_model(
        self,
        store,
        model: str,
        estimated_cost: float,
    ) -> bool:

        if estimated_cost < 0:
            return False

        monthly_budget = float(
            getattr(
                store,
                "monthly_budget",
                0.0,
            )
        )

        used = self.get_monthly_usage(
            store.id
        )

        return (
            used + estimated_cost
            <= monthly_budget
        )


# ---------------------------------
# Cost estimation
# ---------------------------------

def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price: float,
    output_price: float,
) -> float:

    input_tokens = max(
        int(input_tokens),
        0,
    )

    output_tokens = max(
        int(output_tokens),
        0,
    )

    input_price = max(
        float(input_price),
        0.0,
    )

    output_price = max(
        float(output_price),
        0.0,
    )

    cost = (
        (
            input_tokens
            / 1_000_000
        )
        * input_price
    ) + (
        (
            output_tokens
            / 1_000_000
        )
        * output_price
    )

    return round(
        cost,
        10,
    )


def estimate_max_cost(
    input_tokens: int,
    max_output_tokens: int,
    input_price: float,
    output_price: float,
) -> float:

    return estimate_cost(
        input_tokens=input_tokens,
        output_tokens=max_output_tokens,
        input_price=input_price,
        output_price=output_price,
    )


# ---------------------------------
# Conservative token estimation
# ---------------------------------

def estimate_tokens(
    text: str,
) -> int:
    """
    Conservative token estimate without adding
    a tokenizer dependency.

    Rough approximation:
        1 token ~= 4 characters

    We round upward to avoid underestimating
    budget usage.
    """

    if not text:
        return 0

    character_count = len(text)

    return max(
        1,
        (character_count + 3) // 4,
    )


def estimate_messages_tokens(
    messages: list[dict],
) -> int:
    """
    Estimate total input tokens across a list
    of OpenAI-compatible chat messages.

    Includes a small per-message overhead.
    """

    total = 0

    for message in messages:

        role = str(
            message.get(
                "role",
                "",
            )
        )

        content = str(
            message.get(
                "content",
                "",
            )
        )

        total += estimate_tokens(
            role
        )

        total += estimate_tokens(
            content
        )

        # Conservative message formatting overhead.
        total += 4

    return max(
        total,
        1,
    )