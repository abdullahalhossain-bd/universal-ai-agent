import asyncio
import logging
import threading
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.knowledge.chunk import KnowledgeChunk
from app.knowledge.embedding import LocalEmbeddingService

logger = logging.getLogger("app.knowledge.embedding_service")

# Hard cap on batches per backfill run: bounds a pathological loop (e.g. an
# embedding backend that systematically returns fewer vectors than chunks)
# instead of letting one job spin forever while its lock heartbeat renews.
_MAX_BATCHES_PER_RUN = 10_000


class KnowledgeEmbeddingService:

    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

        self.embedding = LocalEmbeddingService()

    def generate_missing_embeddings(
        self,
        store_id: str,
        batch_size: int = 32,
    ) -> int:

        total = 0
        batches = 0

        with Session(self.engine) as session:

            while batches < _MAX_BATCHES_PER_RUN:

                batches += 1

                chunks = (
                    session.query(KnowledgeChunk)
                    .filter(
                        KnowledgeChunk.store_id == store_id,
                        KnowledgeChunk.embedding.is_(None),
                    )
                    .limit(batch_size)
                    .all()
                )

                if not chunks:
                    break

                texts = [
                    chunk.content
                    for chunk in chunks
                ]

                vectors = self.embedding.embed_many(texts)

                if not isinstance(vectors, list) or len(vectors) != len(chunks):
                    # A short/long vector list would otherwise leave the
                    # missing chunks NULL and be re-selected forever. Log,
                    # persist whatever came back, and stop this run.
                    logger.error(
                        "embedding backend returned %s vectors for %s chunks store=%s; stopping this backfill run",
                        len(vectors) if isinstance(vectors, list) else type(vectors).__name__,
                        len(chunks),
                        store_id,
                    )
                    if isinstance(vectors, list):
                        for chunk, vector in zip(chunks, vectors):
                            chunk.embedding = vector
                        session.commit()
                        total += len(vectors)
                    break

                for chunk, vector in zip(chunks, vectors):
                    chunk.embedding = vector

                session.commit()

                total += len(chunks)

            else:
                logger.warning(
                    "embeddings backfill hit the batch cap (%s) store=%s; re-run to continue",
                    _MAX_BATCHES_PER_RUN,
                    store_id,
                )

        return total


_shared_service: KnowledgeEmbeddingService | None = None
_shared_service_lock = threading.Lock()


def get_shared_embedding_service() -> KnowledgeEmbeddingService:
    """Process-wide instance so worker jobs don't build a new engine (and,
    since the model is lazy, load the model) once per crawl/backfill."""
    global _shared_service
    if _shared_service is None:
        with _shared_service_lock:
            if _shared_service is None:
                from app.core.config import settings as _settings
                _shared_service = KnowledgeEmbeddingService(_settings.database_url)
    return _shared_service


async def run_embedding_backfill(job: dict):
    """Background-worker entrypoint for the "knowledge_embeddings" job_type.

    Runs off the request path entirely (enqueued by
    `/v1/knowledge/embeddings/generate` and by `ingest_website` after a
    crawl) and off the worker's event loop thread (the embedding model
    load + encode is CPU-bound, blocking code), so it never stalls an
    API request or the worker's ability to service other concurrent jobs.

    Returns the same shape the worker's dispatch loop already expects
    from `run_website_sync` / `process_sync`: an object with `.errors`,
    `.data_quality` (optionally carrying a "terminal" key so the worker
    acks instead of retrying), `.created`, and `.updated`.
    """
    from app.core.config import settings
    from app.db.database import engine as app_engine
    from app.knowledge.vector_support import resolve_vector_support

    store_id = job.get("store_id") or job.get("tenant_id")
    if not store_id:
        return SimpleNamespace(
            created=0,
            updated=0,
            unchanged=0,
            errors=["knowledge_embeddings job missing store_id"],
            data_quality={"terminal": "missing_store_id"},
        )

    # pgvector must be usable BEFORE we build the service: with the
    # extension missing, knowledge_chunks.embedding is a Text column and
    # every write would fail at flush, retry up to MAX_ATTEMPTS, and land
    # in the DLQ — on every merchant attempt. Keyword search stays fully
    # functional without pgvector, so this is a terminal no-op.
    if not resolve_vector_support(app_engine):
        logger.info("embeddings backfill skipped store=%s reason=pgvector_unavailable", store_id)
        return SimpleNamespace(
            created=0,
            updated=0,
            unchanged=0,
            errors=[],
            data_quality={"terminal": "pgvector_unavailable"},
        )

    try:
        service = get_shared_embedding_service()
    except RuntimeError as exc:
        # sentence-transformers/pgvector are optional dependencies —
        # keyword search keeps working without them. Treat as a
        # terminal no-op rather than retrying forever.
        logger.warning("embeddings backfill skipped store=%s reason=%s", store_id, exc)
        return SimpleNamespace(
            created=0,
            updated=0,
            unchanged=0,
            errors=[],
            data_quality={"terminal": f"embeddings_unavailable: {exc}"},
        )

    count = await asyncio.to_thread(service.generate_missing_embeddings, store_id)
    return SimpleNamespace(created=count, updated=0, unchanged=0, errors=[], data_quality={})
