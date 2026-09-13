import asyncio
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.core.rate_limit import enforce_knowledge_rate_limit
from app.core.tenant import get_current_store
from app.core.features import FEATURE_KNOWLEDGE_BASE, require_feature
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Store
from app.knowledge.search import KnowledgeSearchEngine
from app.knowledge.search_models import KnowledgeSearchRequest
from app.knowledge.vector_search import VectorKnowledgeSearch
from app.knowledge.hybrid_search import HybridKnowledgeSearch
from app.knowledge.chunk import KnowledgePage
from app.knowledge.vector_support import resolve_vector_support
from app.sync.queue import SyncQueue
from app.api.routes.websites import _queue_website

router = APIRouter(prefix="/v1/knowledge", tags=["Knowledge"])

# ---------------------------------------------------------------------------
# Shared search engines
#
# These endpoints previously constructed a new engine (and therefore a new
# SQLAlchemy connection pool, and for the vector/hybrid paths a new
# sentence-transformers model) for EVERY request. That is both a connection
# leak and an easy DoS: one request cost hundreds of MB and seconds of CPU.
# Engines are now process-wide singletons, and the (blocking) search calls
# run in a worker thread so the event loop is never stalled.
# ---------------------------------------------------------------------------
_engine_lock = threading.Lock()
_keyword_engine: KnowledgeSearchEngine | None = None
_vector_engine: VectorKnowledgeSearch | None = None
_hybrid_engine: HybridKnowledgeSearch | None = None


def _get_keyword_engine() -> KnowledgeSearchEngine:
    global _keyword_engine
    if _keyword_engine is None:
        with _engine_lock:
            if _keyword_engine is None:
                _keyword_engine = KnowledgeSearchEngine(settings.database_url)
    return _keyword_engine


def _get_vector_engine() -> VectorKnowledgeSearch:
    global _vector_engine
    if _vector_engine is None:
        with _engine_lock:
            if _vector_engine is None:
                _vector_engine = VectorKnowledgeSearch(settings.database_url)
    return _vector_engine


def _get_hybrid_engine() -> HybridKnowledgeSearch:
    global _hybrid_engine
    if _hybrid_engine is None:
        with _engine_lock:
            if _hybrid_engine is None:
                _hybrid_engine = HybridKnowledgeSearch(settings.database_url)
    return _hybrid_engine


@router.get("/websites")
def list_websites(store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    """Dashboard-facing, strictly store-scoped website knowledge summary."""
    pages = db.query(KnowledgePage.url, KnowledgePage.title, KnowledgePage.crawled_at).filter(KnowledgePage.store_id == store.id).all()
    sites: dict[str, dict] = {}
    for url, title, crawled_at in pages:
        domain = urlparse(url).netloc or url
        entry = sites.setdefault(domain, {"domain": domain, "page_count": 0, "last_crawled_at": None})
        entry["page_count"] += 1
        if crawled_at and (entry["last_crawled_at"] is None or crawled_at > entry["last_crawled_at"]):
            entry["last_crawled_at"] = crawled_at
    return {"count": len(sites), "websites": [{**site, "last_crawled_at": site["last_crawled_at"].isoformat() if site["last_crawled_at"] else None} for site in sorted(sites.values(), key=lambda s: s["domain"])]}


class WebsiteIngestRequest(BaseModel):
    website_url: str = Field(min_length=1, max_length=2048)


@router.post("/ingest")
async def ingest_website(payload: WebsiteIngestRequest, store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    require_feature(store, FEATURE_KNOWLEDGE_BASE)
    try:
        ds, message_id = await _queue_website(payload.website_url, "Website", db, store, required_feature=FEATURE_KNOWLEDGE_BASE)
    except HTTPException:
        raise
    except (ValueError, ConnectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "queued", "datasource_id": ds.id, "message_id": message_id, "pages_found": 0, "pages_created": 0, "chunks_created": 0, "products_found": 0, "message": "Website crawl queued; poll the datasource status for results."}


@router.post("/search")
async def search_knowledge(payload: KnowledgeSearchRequest, store: Store = Depends(get_current_store)):
    await enforce_knowledge_rate_limit(store_id=store.id, plan=store.plan)
    engine = _get_keyword_engine()
    results = await asyncio.to_thread(
        engine.search, store_id=store.id, query=payload.query, limit=payload.limit
    )
    return {"count": len(results), "results": [result.model_dump() for result in results]}


@router.post("/embeddings/generate")
async def generate_embeddings(store: Store = Depends(get_current_store)):
    """Queue a store-wide embeddings backfill.

    The embedding model load + encode is CPU-bound work, so it must
    never run inline on the request; ingestion already triggers this
    automatically after a crawl, so this endpoint exists for merchants
    who need to force a manual backfill (e.g. after pgvector becomes
    available for a store that crawled before it was enabled).
    """
    require_feature(store, FEATURE_KNOWLEDGE_BASE)
    queue = SyncQueue(settings.redis_url)
    try:
        message_id = await queue.enqueue({
            "store_id": store.id,
            "datasource_id": f"embeddings:{store.id}",
            "job_type": "knowledge_embeddings",
        })
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Embeddings queue is temporarily unavailable") from exc
    finally:
        await queue.close()
    return {"status": "queued", "message_id": message_id or "already_queued"}


@router.post("/semantic-search")
async def semantic_search(payload: KnowledgeSearchRequest, store: Store = Depends(get_current_store)):
    await enforce_knowledge_rate_limit(store_id=store.id, plan=store.plan)
    # Fail fast (and cheap) when pgvector/sentence-transformers are not
    # available instead of letting the raw SQL error surface as a 500.
    from app.db.database import engine as app_engine

    if not resolve_vector_support(app_engine):
        raise HTTPException(status_code=503, detail="Semantic search is unavailable: pgvector is not enabled on this deployment")
    try:
        engine = _get_vector_engine()
        results = await asyncio.to_thread(
            engine.search, store_id=store.id, query=payload.query, limit=payload.limit
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Covers pgvector-off deployments resolved late (TEXT column) and
        # model-load failures: degrade to a clean 503, never a 500.
        raise HTTPException(status_code=503, detail="Semantic search is temporarily unavailable") from exc
    return {"count": len(results), "results": results}


@router.post("/hybrid-search")
async def hybrid_search(payload: KnowledgeSearchRequest, store: Store = Depends(get_current_store)):
    await enforce_knowledge_rate_limit(store_id=store.id, plan=store.plan)
    try:
        engine = _get_hybrid_engine()
        results = await asyncio.to_thread(
            engine.search, store_id=store.id, query=payload.query, limit=payload.limit
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    normalized = [result.model_dump() if hasattr(result, "model_dump") else result for result in results]
    return {"count": len(normalized), "results": normalized}
