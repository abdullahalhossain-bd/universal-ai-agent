class VectorSearchProvider:

    def __init__(
        self,
        repository,
        embedding_provider,
    ):

        self.repository = repository

        self.embedding = (
            embedding_provider
        )

    async def search(
        self,
        query,
        limit=10,
    ):

        vector = await (
            self.embedding.embed(
                [query]
            )
        )

        return await (
            self.repository
            .vector_search(
                vector=vector[0],
                limit=limit,
            )
        )
