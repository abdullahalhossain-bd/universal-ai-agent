from pydantic import BaseModel


class ResponseProduct(BaseModel):

    id: str
    name: str

    price: float | None = None
    stock: int | None = None

    images: list[str] = []

    url: str | None = None


class ResponseSource(BaseModel):

    type: str
    title: str | None = None
    url: str | None = None


class GeneratedResponse(BaseModel):

    message: str

    products: list[ResponseProduct] = []

    sources: list[ResponseSource] = []

    used_llm: bool = False

    provider: str | None = None
