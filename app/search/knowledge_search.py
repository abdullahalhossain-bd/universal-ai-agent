from app.search.base import (
    SearchProvider,
)


class KnowledgeSearchProvider(
    SearchProvider
):

    def __init__(
        self,
        repository,
    ):

        self.repository = repository

    async def search(
        self,
        query: str,
        limit: int = 10,
    ):

        return await (
            self.repository.search(
                query=query,
                limit=limit,
            )
        )
