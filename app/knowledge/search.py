"""
Keyword-based website knowledge search.
"""

from sqlalchemy import create_engine, text

from app.knowledge.search_models import (
    KnowledgeSearchResult,
)


class KnowledgeSearchEngine:

    def __init__(
        self,
        database_url: str,
    ):
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

    def search(
        self,
        store_id: str,
        query: str,
        limit: int = 5,
    ) -> list[KnowledgeSearchResult]:

        sql = text(
            """
            SELECT
                kc.id AS chunk_id,
                kc.page_id,
                kp.url,
                kp.title,
                kc.content,
                ts_rank_cd(
                    to_tsvector(
                        'simple',
                        kc.content
                    ),
                    plainto_tsquery(
                        'simple',
                        :query
                    )
                ) AS score
            FROM knowledge_chunks kc
            JOIN knowledge_pages kp
                ON kp.id = kc.page_id
            WHERE
                kc.store_id = :store_id
                AND kc.content ILIKE :like_query
            ORDER BY score DESC
            LIMIT :limit
            """
        )

        like_pattern = f"%{query}%"

        with self.engine.connect() as conn:

            rows = (
                conn.execute(
                    sql,
                    {
                        "store_id": store_id,
                        "query": query,
                        "like_query": like_pattern,
                        "limit": limit,
                    },
                )
                .mappings()
                .all()
            )

        return [
            KnowledgeSearchResult(
                chunk_id=row["chunk_id"],
                page_id=row["page_id"],
                url=row["url"],
                title=row["title"],
                content=row["content"],
                score=float(
                    row["score"] or 0.0
                ),
            )
            for row in rows
        ]


KnowledgeSearch = KnowledgeSearchEngine