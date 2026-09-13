from app.planner.rule_planner import (
    plan as rule_plan,
)


class QueryPlanner:

    def __init__(
        self,
        llm_planner=None,
    ):

        self.llm_planner = llm_planner

    async def plan(
        self,
        query: str,
    ):

        result = rule_plan(query)

        if result.confidence >= 0.80:

            return result

        if self.llm_planner:

            return await (
                self.llm_planner.plan(
                    query
                )
            )

        return result
