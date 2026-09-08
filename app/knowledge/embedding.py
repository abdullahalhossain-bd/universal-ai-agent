"""
Local embedding service backed by `sentence_transformers`.

`sentence_transformers` is a heavy dependency (it pulls in torch, etc.).
We import it lazily inside `__init__` so that the rest of the knowledge
subsystem keeps working even when the package isn't installed — callers
that try to instantiate `LocalEmbeddingService` without the dep will get
a clear error.
"""

from typing import Any


class LocalEmbeddingService:
    """
    Wraps `sentence_transformers.SentenceTransformer` for short text →
    vector embedding. The model is loaded lazily on first use.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        try:
            from sentence_transformers import (
                SentenceTransformer,
            )
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for local "
                "embedding. Install it with: "
                "pip install sentence-transformers"
            ) from exc

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return vector.tolist()

    def embed_many(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
        )
        return vectors.tolist()
