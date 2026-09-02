class HybridRanker:
    """
    Combines keyword-search and vector-search results into a single
    ranked list.

    IMPORTANT: keyword scores and vector scores usually live on very
    different scales (e.g. keyword/BM25-style scores can be large and
    unbounded, while vector similarity is typically 0-1 cosine
    similarity). Combining raw scores with weights would let one
    signal silently dominate regardless of the configured weights.
    To fix this, each result list is min-max normalized to a 0-1
    range *before* the weights are applied, so keyword_weight and
    vector_weight actually reflect the intended balance.
    """

    def __init__(
        self,
        keyword_weight=0.4,
        vector_weight=0.6,
    ):

        self.keyword_weight = (
            keyword_weight
        )

        self.vector_weight = (
            vector_weight
        )

    def rank(
        self,
        keyword_results,
        vector_results,
        limit=10,
    ):

        normalized_keyword = self._normalize(
            keyword_results
        )

        normalized_vector = self._normalize(
            vector_results
        )

        scores = {}

        items = {}

        for result in keyword_results:

            key = self._key(result)

            scores[key] = (
                scores.get(key, 0)
                + self.keyword_weight
                * normalized_keyword[key]
            )

            items[key] = result

        for result in vector_results:

            key = self._key(result)

            scores[key] = (
                scores.get(key, 0)
                + self.vector_weight
                * normalized_vector[key]
            )

            items[key] = result

        # Precompute (score, item) pairs once instead of
        # re-looking-up the score inside the sort comparator.
        scored_items = [
            (scores[key], item)
            for key, item in items.items()
        ]

        scored_items.sort(
            key=lambda pair: pair[0],
            reverse=True,
        )

        ranked = [
            item
            for _, item in scored_items
        ]

        return ranked[:limit]

    def _normalize(
        self,
        results,
    ):
        """
        Min-max normalize raw scores for a result list to the
        0-1 range, keyed by self._key(result).

        - Empty list -> {}
        - All-equal scores (including a single result) -> everyone
          gets 1.0, so that signal still contributes fully instead
          of collapsing to 0 (which a naive (x-min)/(max-min) would
          do when max == min).
        """

        if not results:
            return {}

        raw_scores = {
            self._key(result): result.score
            for result in results
        }

        min_score = min(raw_scores.values())
        max_score = max(raw_scores.values())

        score_range = max_score - min_score

        if score_range == 0:
            return {
                key: 1.0
                for key in raw_scores
            }

        return {
            key: (value - min_score) / score_range
            for key, value in raw_scores.items()
        }

    def _key(
        self,
        result,
    ):

        return (
            result.metadata or {}
        ).get(
            "chunk_id",
            result.content[:100],
        )