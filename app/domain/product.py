from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductVariant:
    id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    price: float | None = None
    stock: float | None = None


@dataclass
class Product:
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

    variants: list[ProductVariant] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)
