from dataclasses import dataclass


@dataclass
class SearchResult:

    source_type: str

    title: str | None

    content: str

    score: float

    url: str | None = None

    metadata: dict | None = None
