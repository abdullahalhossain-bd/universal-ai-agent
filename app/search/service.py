import asyncio


class UnifiedSearchService:

    def __init__(
        self,
        product_search,
        knowledge_search,
        vector_search,
        ranker,
    ):

        self.product_search = (
            product_search
        )

        self.knowledge_search = (
            knowledge_search
        )

        self.vector_search = (
            vector_search
        )

        self.ranker = ranker

    async def search(
        self,
        query,
        search_products=True,
        search_knowledge=True,
        limit=10,
    ):

        tasks = []

        if search_products:

            tasks.append(
                self.product_search.search(
                    query,
                    limit,
                )
            )

        if search_knowledge:

            tasks.append(
                self.knowledge_search.search(
                    query,
                    limit,
                )
            )

        results = await asyncio.gather(
            *tasks
        )

        combined = []

        for result_set in results:

            combined.extend(
                result_set
            )

        return combined[:limit]
