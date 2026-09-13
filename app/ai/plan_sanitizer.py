from app.ai.llm_plan import (
    LLMQueryPlan,
)

from app.ai.sanitizer import (
    QuerySanitizer,
)


class PlanSanitizer:

    def __init__(self):

        self.sanitizer = (
            QuerySanitizer()
        )

    def clean(
        self,
        plan: LLMQueryPlan,
    ):

        for action in plan.actions:

            action.query = (
                self.sanitizer.clean(
                    action.query
                )
            )

            action.filters = (
                self.sanitizer.clean_filters(
                    action.filters
                )
            )

        return plan
