from app.planner.rule_planner import plan as rule_plan


class QueryPlanner:
    """Deterministic-first planner with optional structured LLM fallback."""

    def __init__(self, llm_planner=None):
        self.llm_planner = llm_planner

    async def plan(self, query: str):
        deterministic = rule_plan(query)

        # High-confidence rules avoid unnecessary LLM cost/latency.
        if deterministic.confidence >= 0.80 or self.llm_planner is None:
            return deterministic

        try:
            llm_result = await self.llm_planner.plan(query)
        except Exception:
            # LLM outage, timeout, missing key or malformed output must never
            # make product search unavailable. Keep the deterministic result.
            return deterministic

        # Only accept the typed planner result. An LLM must not be able to
        # smuggle arbitrary actions/SQL into the search pipeline.
        if llm_result is None:
            return deterministic
        return llm_result
