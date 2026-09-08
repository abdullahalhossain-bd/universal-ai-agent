from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.knowledge.chunk import KnowledgeChunk
from app.knowledge.embedding import LocalEmbeddingService


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

        with Session(self.engine) as session:

            while True:

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

                for chunk, vector in zip(chunks, vectors):
                    chunk.embedding = vector

                session.commit()

                total += len(chunks)

        return total