from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.core.tenant import get_current_store
from app.core.features import FEATURE_KNOWLEDGE_BASE, require_feature
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Store
from app.knowledge.search import KnowledgeSearchEngine
from app.knowledge.search_models import KnowledgeSearchRequest
from app.knowledge.embedding_service import KnowledgeEmbeddingService
from app.knowledge.vector_search import VectorKnowledgeSearch
from app.knowledge.hybrid_search import HybridKnowledgeSearch
from app.knowledge.chunk import KnowledgePage
from app.api.routes.websites import _queue_website

router = APIRouter(prefix="/v1/knowledge", tags=["Knowledge"])


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
    engine = KnowledgeSearchEngine(settings.database_url)
    results = engine.search(store_id=store.id, query=payload.query, limit=payload.limit)
    return {"count": len(results), "results": [result.model_dump() for result in results]}


@router.post("/embeddings/generate")
async def generate_embeddings(store: Store = Depends(get_current_store)):
    try:
        service = KnowledgeEmbeddingService(settings.database_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    count = service.generate_missing_embeddings(store_id=store.id)
    return {"embeddings_created": count}


@router.post("/semantic-search")
async def semantic_search(payload: KnowledgeSearchRequest, store: Store = Depends(get_current_store)):
    try:
        engine = VectorKnowledgeSearch(settings.database_url)
        results = engine.search(store_id=store.id, query=payload.query, limit=payload.limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"count": len(results), "results": results}


@router.post("/hybrid-search")
async def hybrid_search(payload: KnowledgeSearchRequest, store: Store = Depends(get_current_store)):
    try:
        engine = HybridKnowledgeSearch(settings.database_url)
        results = engine.search(store_id=store.id, query=payload.query, limit=payload.limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    normalized = [result.model_dump() if hasattr(result, "model_dump") else result for result in results]
    return {"count": len(normalized), "results": normalized}
