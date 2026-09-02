from app.knowledge.search import (
    KnowledgeSearchEngine,
)

from app.knowledge.vector_search import (
    VectorKnowledgeSearch,
)


class HybridKnowledgeSearch:

    def __init__(
        self,
        database_url: str,
    ):
        self.keyword = (
            KnowledgeSearchEngine(
                database_url
            )
        )

        self.vector = (
            VectorKnowledgeSearch(
                database_url
            )
        )

    def search(
        self,
        store_id: str,
        query: str,
        limit: int = 5,
    ):

        keyword_results = (
            self.keyword.search(
                store_id=store_id,
                query=query,
                limit=limit * 2,
            )
        )

        # Vector search is optional: it requires the pgvector
        # extension and sentence-transformers. When either is
        # unavailable (or the vector query fails), fall back to
        # keyword-only results instead of erroring the endpoint.
        try:
            vector_results = (
                self.vector.search(
                    store_id=store_id,
                    query=query,
                    limit=limit * 2,
                )
            )
        except Exception:
            vector_results = []

        # Vector search is currently disabled.
        # Keyword results are therefore the safe fallback.
        if not vector_results:

            return keyword_results[:limit]

        merged = {}

        for result in keyword_results:

            merged[
                result.chunk_id
            ] = {
                "result": result,
                "keyword_score": result.score,
                "vector_score": 0.0,
            }

        for result in vector_results:

            if result["chunk_id"] in merged:

                merged[
                    result["chunk_id"]
                ]["vector_score"] = (
                    result["score"]
                )

            else:

                merged[
                    result["chunk_id"]
                ] = {
                    "result": result,
                    "keyword_score": 0.0,
                    "vector_score": result["score"],
                }

        ranked = []

        for item in merged.values():

            final_score = (
                0.35
                * item["keyword_score"]
                + 0.65
                * item["vector_score"]
            )

            result = item["result"]

            if hasattr(
                result,
                "model_copy",
            ):

                result = result.model_copy(
                    update={
                        "score": final_score,
                    }
                )

            elif isinstance(
                result,
                dict,
            ):

                result = dict(result)

                result["score"] = (
                    final_score
                )

            ranked.append(result)

        def _score_key(item):

            score = getattr(
                item,
                "score",
                None,
            )

            if (
                score is None
                and isinstance(
                    item,
                    dict,
                )
            ):

                score = item.get(
                    "score",
                    0.0,
                )

            return score or 0.0

        ranked.sort(
            key=_score_key,
            reverse=True,
        )

        return ranked[:limit]