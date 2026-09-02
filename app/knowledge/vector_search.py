from sqlalchemy import create_engine, text

from app.knowledge.embedding import LocalEmbeddingService


class VectorKnowledgeSearch:

    def __init__(self, database_url: str):

        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

        self.embedding = LocalEmbeddingService()

    def search(
        self,
        store_id: str,
        query: str,
        limit: int = 5,
    ):

        query_vector = self.embedding.embed(query)

        sql = text(
            """
            SELECT
                kc.id AS chunk_id,
                kc.page_id,
                kp.url,
                kp.title,
                kc.content,

                1 - (
                    kc.embedding
                    <=> CAST(
                        :embedding AS vector
                    )
                ) AS score

            FROM knowledge_chunks kc

            JOIN knowledge_pages kp
                ON kp.id = kc.page_id

            WHERE
                kc.store_id = :store_id
                AND kc.embedding IS NOT NULL

            ORDER BY
                kc.embedding
                <=> CAST(
                    :embedding AS vector
                )

            LIMIT :limit
            """
        )

        with self.engine.connect() as conn:

            rows = (
                conn.execute(
                    sql,
                    {
                        "store_id": store_id,
                        "embedding": str(query_vector),
                        "limit": limit,
                    },
                )
                .mappings()
                .all()
            )

        return [
            {
                "chunk_id": row["chunk_id"],
                "page_id": row["page_id"],
                "url": row["url"],
                "title": row["title"],
                "content": row["content"],
                "score": float(row["score"]),
            }
            for row in rows
        ]