from app.ai.intent_models import (
    IntentResult,
    IntentType,
)

from app.ai.query_plan import (
    ActionType,
    QueryAction,
    QueryPlan,
)


class QueryPlanner:

    def create_plan(
        self,
        intent: IntentResult,
    ) -> QueryPlan:

        actions = []

        filters = (
            intent.filters.model_dump(
                exclude_none=True
            )
        )

        for item in intent.intents:

            if (
                item
                == IntentType.PRODUCT_SEARCH
            ):

                actions.append(
                    QueryAction(
                        action=(
                            ActionType
                            .PRODUCT_SEARCH
                        ),
                        parameters=filters,
                    )
                )

            elif (
                item
                == IntentType.PRODUCT_LOOKUP
            ):

                actions.append(
                    QueryAction(
                        action=(
                            ActionType
                            .PRODUCT_LOOKUP
                        ),
                        parameters=filters,
                    )
                )

            elif (
                item
                == IntentType.STOCK_CHECK
            ):

                actions.append(
                    QueryAction(
                        action=(
                            ActionType
                            .STOCK_CHECK
                        ),
                        parameters=filters,
                    )
                )

            elif (
                item
                == IntentType.WEBSITE_KNOWLEDGE
            ):

                actions.append(
                    QueryAction(
                        action=(
                            ActionType
                            .KNOWLEDGE_SEARCH
                        ),
                        parameters={},
                    )
                )

        return QueryPlan(
            actions=actions
        )
