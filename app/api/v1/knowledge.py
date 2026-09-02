from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
)

from app.auth.dependency import (
    authenticate_api_key,
)

from app.core.tenant import (
    get_current_store,
)

from app.core.features import (
    FEATURE_KNOWLEDGE_BASE,
    require_feature,
)

from app.core.config import settings

from app.db.database import get_db

from app.db.models import APIKey, Store

from sqlalchemy.orm import Session

from app.knowledge.service import (
    KnowledgeService,
)

from app.knowledge.search import (
    KnowledgeSearchEngine,
)

from app.knowledge.search_models import (
    KnowledgeSearchRequest,
)

from app.knowledge.embedding_service import (
    KnowledgeEmbeddingService,
)

from app.knowledge.vector_search import (
    VectorKnowledgeSearch,
)

from app.knowledge.hybrid_search import (
    HybridKnowledgeSearch,
)


router = APIRouter(
    prefix="/v1/knowledge",
    tags=["Knowledge"],
)


@router.get("/websites")
def list_websites(
    store: Store = Depends(
        get_current_store
    ),
    db: Session = Depends(get_db),
):
    """
    Dashboard-facing summary of everything /ingest has crawled for
    this store so far, grouped by domain (a single `/ingest` call can
    crawl many pages under one site). Read-only, store-scoped.
    """
    from urllib.parse import urlparse
    from sqlalchemy import func

    from app.knowledge.chunk import KnowledgePage

    pages = (
        db.query(
            KnowledgePage.url,
            KnowledgePage.title,
            KnowledgePage.crawled_at,
        )
        .filter(KnowledgePage.store_id == store.id)
        .all()
    )

    sites: dict[str, dict] = {}
    for url, title, crawled_at in pages:
        domain = urlparse(url).netloc or url
        entry = sites.setdefault(
            domain,
            {"domain": domain, "page_count": 0, "last_crawled_at": None},
        )
        entry["page_count"] += 1
        if crawled_at and (
            entry["last_crawled_at"] is None or crawled_at > entry["last_crawled_at"]
        ):
            entry["last_crawled_at"] = crawled_at

    _ = func  # imported for symmetry with the rest of the codebase's query style

    return {
        "count": len(sites),
        "websites": [
            {
                **site,
                "last_crawled_at": (
                    site["last_crawled_at"].isoformat() if site["last_crawled_at"] else None
                ),
            }
            for site in sorted(sites.values(), key=lambda s: s["domain"])
        ],
    }


class WebsiteIngestRequest(BaseModel):

    website_url: HttpUrl


@router.post("/ingest")
async def ingest_website(
    payload: WebsiteIngestRequest,
    store: Store = Depends(
        get_current_store
    ),
):

    require_feature(store, FEATURE_KNOWLEDGE_BASE)

    service = KnowledgeService(
        settings.database_url
    )

    try:
        result = await service.ingest(
            store_id=store.id,
            website_url=str(
                payload.website_url
            ),
        )
    except ValueError as exc:
        # SSRF guard: private/internal/unresolvable targets are
        # refused by the crawler. A client mistake — 400, not 500.
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return result


@router.post("/search")
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    api_key: APIKey = Depends(
        authenticate_api_key
    ),
):

    engine = KnowledgeSearchEngine(
        settings.database_url
    )

    results = engine.search(
        store_id=api_key.store_id,
        query=payload.query,
        limit=payload.limit,
    )

    return {
        "count": len(results),
        "results": [
            result.model_dump()
            for result in results
        ],
    }


@router.post("/embeddings/generate")
async def generate_embeddings(
    api_key: APIKey = Depends(
        authenticate_api_key
    ),
):
    try:
        service = KnowledgeEmbeddingService(
            settings.database_url
        )
    except RuntimeError as exc:
        # sentence-transformers not installed.
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    count = (
        service.generate_missing_embeddings(
            store_id=api_key.store_id
        )
    )

    return {
        "embeddings_created": count,
    }


@router.post("/semantic-search")
async def semantic_search(
    payload: KnowledgeSearchRequest,
    api_key: APIKey = Depends(
        authenticate_api_key
    ),
):
    try:
        engine = VectorKnowledgeSearch(
            settings.database_url
        )
    except RuntimeError as exc:
        # sentence-transformers not installed.
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    results = engine.search(
        store_id=api_key.store_id,
        query=payload.query,
        limit=payload.limit,
    )

    return {
        "count": len(results),
        "results": results,
    }


@router.post("/hybrid-search")
async def hybrid_search(
    payload: KnowledgeSearchRequest,
    api_key: APIKey = Depends(
        authenticate_api_key
    ),
):

    try:
        # Construction can already raise: the hybrid engine
        # instantiates the vector path, which requires
        # sentence-transformers. Cover BOTH construction and
        # search with the same graceful-degradation contract.
        engine = HybridKnowledgeSearch(
            settings.database_url
        )

        results = engine.search(
            store_id=api_key.store_id,
            query=payload.query,
            limit=payload.limit,
        )
    except RuntimeError as exc:
        # sentence-transformers not installed — same graceful
        # degradation contract as /semantic-search.
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    normalized = []

    for result in results:

        if hasattr(
            result,
            "model_dump",
        ):

            normalized.append(
                result.model_dump()
            )

        else:

            normalized.append(result)

    return {
        "count": len(normalized),
        "results": normalized,
    }