import json

from app.ai.llm_plan import (
    LLMQueryPlan,
)

from app.ai.prompts import (
    QUERY_PLANNER_SYSTEM_PROMPT,
)


class LLMQueryPlanner:

    def __init__(
        self,
        provider,
    ):
        self.provider = provider

    async def create_plan(
        self,
        query: str,
    ) -> LLMQueryPlan:

        response = await self.provider.generate(
            system_prompt=(
                QUERY_PLANNER_SYSTEM_PROMPT
            ),
            user_prompt=query,
        )

        try:

            data = json.loads(
                response
            )

        except json.JSONDecodeError:

            raise ValueError(
                "LLM returned invalid JSON"
            )

        return LLMQueryPlan.model_validate(
            data
        )
