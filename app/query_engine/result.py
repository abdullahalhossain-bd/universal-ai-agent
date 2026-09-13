from pydantic import BaseModel


class SourceRef(BaseModel):

    type: str = "source"
    title: str
    url: str | None = None


class AnswerBlock(BaseModel):

    type: str
    text: str | None = None
    items: list[dict] | None = None


class QueryEngineResult(BaseModel):

    message: str
    blocks: list[AnswerBlock] = []
    sources: list[SourceRef] = []
