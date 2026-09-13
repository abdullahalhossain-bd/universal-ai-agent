"""
Website-knowledge search tool for the (currently unwired) query_engine
plan executor. Delegates to the same `KnowledgeSearchEngine` the live
chat path uses (app/knowledge/search.py) — no second search
implementation.

Output shape is intentionally flat (`answer` + `source`) to match what
`app.query_engine.composer.compose_answer` already expects to find
under the "knowledge_search" key; `results` carries the full ranked
list for callers that want more than the top hit.
"""

from __future__ import annotations

from app.query_engine.tools.base import BaseTool
from app.knowledge.search import KnowledgeSearchEngine
from app.core.config import settings


class KnowledgeSearchTool(BaseTool):

    name = "knowledge_search"
    description = "Search website knowledge base (policies, FAQ, delivery, etc.)"

    def __init__(self, search_engine: KnowledgeSearchEngine | None = None):
        # `KnowledgeSearchEngine.__init__` only builds a SQLAlchemy
        # engine (no eager connection — see app/knowledge/search.py),
        # so constructing a default instance here is safe even before
        # any DB is reachable, matching how `ChatService` lazily
        # builds its own shared instance from the same setting.
        self._search_engine = (
            search_engine
            or KnowledgeSearchEngine(settings.database_url)
        )

    def bind_search_engine(
        self, search_engine: KnowledgeSearchEngine
    ) -> "KnowledgeSearchTool":
        self._search_engine = search_engine
        return self

    async def execute(
        self,
        tenant_id: str,
        query: str | None = None,
        limit: int = 5,
        **kwargs,
    ):
        if not query:
            return {"error": "query is required"}

        results = self._search_engine.search(
            store_id=tenant_id,
            query=query,
            limit=limit,
        )

        if not results:
            return {"answer": None, "source": None, "results": []}

        top = results[0]

        return {
            "answer": top.content,
            "source": {
                "title": top.title,
                "url": top.url,
            },
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "page_id": r.page_id,
                    "url": r.url,
                    "title": r.title,
                    "content": r.content,
                    "score": r.score,
                }
                for r in results
            ],
        }
