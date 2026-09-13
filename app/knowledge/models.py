from datetime import datetime

from pydantic import BaseModel


class KnowledgePage(BaseModel):

    id: str | None = None

    store_id: str

    url: str

    title: str | None = None

    content: str

    content_hash: str

    page_type: str = "unknown"

    language: str | None = None

    status: str = "active"

    http_status: int | None = None

    crawled_at: datetime | None = None


class KnowledgeChunk(BaseModel):

    id: str | None = None

    store_id: str

    page_id: str

    url: str

    title: str | None = None

    chunk_index: int

    content: str

    embedding: list[float] | None = None