from decimal import Decimal
from pydantic import BaseModel, Field


class ProductImage(BaseModel):
    url: str
    alt: str | None = None


class ProductVariant(BaseModel):
    id: str
    name: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    stock: int | None = None


class UniversalProduct(BaseModel):
    id: str
    name: str
    description: str | None = None

    price: Decimal | None = None
    currency: str | None = None

    stock: int | None = None
    sku: str | None = None

    category: str | None = None
    brand: str | None = None

    images: list[ProductImage] = Field(default_factory=list)
    variants: list[ProductVariant] = Field(default_factory=list)

    url: str | None = None

    source_metadata: dict = Field(default_factory=dict)