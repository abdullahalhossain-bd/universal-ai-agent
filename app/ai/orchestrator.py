from app.ai.planner import QueryPlanner
from app.ai.rule_router import (
    RuleIntentRouter,
)


class QueryOrchestrator:

    def __init__(self):

        self.router = (
            RuleIntentRouter()
        )

        self.planner = (
            QueryPlanner()
        )

    def analyze(
        self,
        query: str,
    ):

        intent = self.router.route(
            query
        )

        plan = self.planner.create_plan(
            intent
        )

        return {
            "query": query,
            "intent": intent.model_dump(),
            "plan": plan.model_dump(),
        }
