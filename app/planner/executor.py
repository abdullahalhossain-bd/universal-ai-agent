class ActionExecutor:

    def __init__(
        self,
        product_search,
        knowledge_search,
    ):

        self.product_search = (
            product_search
        )

        self.knowledge_search = (
            knowledge_search
        )

    async def execute(
        self,
        action,
    ):

        results = []

        if action.product_filters:

            products = await (
                self.product_search.search(
                    action.product_filters
                )
            )

            results.extend(products)

        if action.knowledge_query:

            knowledge = await (
                self.knowledge_search.search(
                    action.knowledge_query
                )
            )

            results.extend(knowledge)

        return results
