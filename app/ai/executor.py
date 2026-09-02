from app.ai.query_plan import (
    ActionType,
)
from app.ai.context_builder import (
    ContextBuilder,
)


class QueryExecutor:

    def __init__(
        self,
        product_service=None,
        knowledge_search=None,
    ):

        self.product_service = (
            product_service
        )

        self.knowledge_search = (
            knowledge_search
        )

        self.context_builder = (
            ContextBuilder()
        )

    def execute(
        self,
        query: str,
        plan,
    ):

        products = []
        knowledge = []

        for action in plan.actions:

            if (
                action.action
                == ActionType.PRODUCT_SEARCH
            ):

                products.extend(
                    self.product_service.search(
                        query=query,
                        **action.parameters,
                    )
                )

            elif (
                action.action
                == ActionType.KNOWLEDGE_SEARCH
            ):

                knowledge.extend(
                    self.knowledge_search.search(
                        tenant_id=(
                            action.parameters
                            .get("tenant_id")
                        ),
                        query=query,
                        limit=5,
                    )
                )

        return self.context_builder.build(
            query=query,
            products=products,
            knowledge=knowledge,
        )
