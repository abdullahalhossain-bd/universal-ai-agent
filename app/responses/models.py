from pydantic import BaseModel, Field


class ProductCard(BaseModel):

    id: str
    name: str

    price: float | None = None
    currency: str | None = None

    stock: float | None = None

    image_url: str | None = None
    product_url: str | None = None

    brand: str | None = None
    category: str | None = None


class ChatResponse(BaseModel):

    message: str

    intent: str

    products: list[ProductCard] = Field(
        default_factory=list
    )

    metadata: dict = Field(
        default_factory=dict
    )
