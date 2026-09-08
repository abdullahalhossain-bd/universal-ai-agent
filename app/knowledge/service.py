import hashlib

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.knowledge.chunk import (
    KnowledgeChunk,
)
from app.knowledge.chunker import (
    TextChunker,
)
from app.knowledge.crawler import (
    WebsiteCrawler,
)
from app.knowledge.chunk import (
    KnowledgePage,
)


class KnowledgeService:

    def __init__(
        self,
        database_url: str,
    ):
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

        self.crawler = WebsiteCrawler(
            max_pages=50
        )

        self.chunker = TextChunker()

    async def ingest(
        self,
        store_id: str,
        website_url: str,
    ):

        pages = await self.crawler.crawl(
            website_url
        )

        created_pages = 0
        created_chunks = 0

        with Session(
            self.engine
        ) as session:

            for page in pages:

                content_hash = hashlib.sha256(
                    page["content"]
                    .encode("utf-8")
                ).hexdigest()

                existing = (
                    session.query(
                        KnowledgePage
                    )
                    .filter(
                        KnowledgePage.store_id
                        == store_id,
                        KnowledgePage.url
                        == page["url"],
                    )
                    .first()
                )

                if existing:

                    if (
                        existing.content_hash
                        == content_hash
                    ):
                        continue

                    existing.content = (
                        page["content"]
                    )

                    existing.title = (
                        page["title"]
                    )

                    existing.content_hash = (
                        content_hash
                    )

                    existing.http_status = (
                        page.get("http_status")
                    )

                    page_id = existing.id

                    session.query(
                        KnowledgeChunk
                    ).filter(
                        KnowledgeChunk.page_id
                        == page_id
                    ).delete(
                        synchronize_session=False
                    )

                else:

                    knowledge_page = (
                        KnowledgePage(
                            store_id=store_id,
                            url=page["url"],
                            title=page.get(
                                "title"
                            ),
                            content=page["content"],
                            content_hash=content_hash,
                            http_status=page.get(
                                "http_status"
                            ),
                        )
                    )

                    session.add(
                        knowledge_page
                    )

                    session.flush()

                    page_id = (
                        knowledge_page.id
                    )

                    created_pages += 1

                chunks = (
                    self.chunker.split(
                        page["content"]
                    )
                )

                for index, chunk in enumerate(
                    chunks
                ):

                    session.add(
                        KnowledgeChunk(
                            store_id=store_id,
                            page_id=page_id,
                            chunk_index=index,
                            content=chunk,
                        )
                    )

                    created_chunks += 1

            session.commit()

        return {
            "pages_found": len(pages),
            "pages_created": created_pages,
            "chunks_created": created_chunks,
        }