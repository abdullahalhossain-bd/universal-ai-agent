from pydantic import BaseModel


class UnifiedSearchRequest(BaseModel):

    query: str

    search_products: bool = True

    search_knowledge: bool = True

    limit: int = 10
