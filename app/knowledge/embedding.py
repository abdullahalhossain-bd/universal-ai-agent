"""
Local embedding service backed by `sentence_transformers`.

`sentence_transformers` is a heavy dependency (it pulls in torch, etc.).
We import it lazily and load the model on first use so that the rest of
the knowledge subsystem keeps working even when the package isn't
installed — callers that try to embed without the dep will get a clear
error. The lazy load also keeps request-path construction cheap: only
an actual embed() call pays for the model load, and a shared service
instance loads it exactly once per process.
"""

import threading
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
        self.model_name = model_name
        self._model: Any = None
        self._model_lock = threading.Lock()

    def _load_model(self):
        # Double-checked locking: concurrent first callers (worker
        # threads, asyncio.to_thread) must not each load a full model.
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
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
            self._model = SentenceTransformer(self.model_name)
            return self._model

    def _require_model(self):
        if self._model is None:
            return self._load_model()
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._require_model()
        vector = model.encode(
            text,
            normalize_embeddings=True,
        )
        return vector.tolist()

    def embed_many(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        model = self._require_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
        )
        return vectors.tolist()
