from pydantic import BaseModel


class ProductCard(BaseModel):

    id: str
    name: str
    price: float | None = None
    currency: str | None = None
    stock: int | None = None
    image_url: str | None = None
    product_url: str | None = None


class ProductCardsBlock(BaseModel):

    type: str = "product_cards"
    items: list[ProductCard] = []


class ChatResponse(BaseModel):

    message: str
    blocks: list[dict] = []
