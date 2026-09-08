from pydantic import BaseModel


class ProductVariant(BaseModel):

    id: str
    product_id: str

    attributes: dict = {}

    price: float | None = None
    stock: float | None = None


class Product(BaseModel):

    id: str
    name: str
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    stock: float | None = None
    sku: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    category: str | None = None
    brand: str | None = None
    variants: list[ProductVariant] = []
