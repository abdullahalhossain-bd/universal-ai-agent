import json

from app.ai.llm_plan import LLMQueryPlan
from app.ai.plan_sanitizer import PlanSanitizer
from app.ai.prompts import QUERY_PLANNER_SYSTEM_PROMPT


class LLMQueryPlanner:
    """Convert natural language into validated search actions only."""

    def __init__(self, provider):
        self.provider = provider
        self.sanitizer = PlanSanitizer()

    async def create_plan(self, query: str) -> LLMQueryPlan:
        response = await self.provider.generate(
            system_prompt=QUERY_PLANNER_SYSTEM_PROMPT,
            user_prompt=query,
        )

        try:
            data = json.loads(response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("LLM returned invalid JSON") from exc

        plan = LLMQueryPlan.model_validate(data)
        return self.sanitizer.clean(plan)

    async def plan(self, query: str) -> LLMQueryPlan:
        # QueryPlanner uses this interface; keep create_plan for compatibility.
        return await self.create_plan(query)
