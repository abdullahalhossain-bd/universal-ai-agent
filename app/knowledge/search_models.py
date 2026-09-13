from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):

    # Deprecated: accepted for backward compatibility but IGNORED.
    # The authenticated store (from the API key) always scopes the
    # search, so one store can never read another store's knowledge.
    store_id: str | None = None

    query: str

    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class KnowledgeSearchResult(BaseModel):

    chunk_id: str

    page_id: str

    url: str

    title: str | None = None

    content: str

    score: float