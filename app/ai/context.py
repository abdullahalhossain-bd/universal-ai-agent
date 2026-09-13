from pydantic import BaseModel


class ContextItem(BaseModel):

    source_type: str

    content: str

    metadata: dict = {}

    relevance: float = 0.0
