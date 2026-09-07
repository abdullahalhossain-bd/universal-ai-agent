from dataclasses import dataclass


@dataclass
class UniversalProduct:
    """Connector-independent product representation.

    raw_data is retained so connector-specific fields are never silently
    discarded at the product-search boundary.
    """

    id: str
    name: str
    price: float | None = None
    stock: int | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    attributes: dict | None = None
    image_url: str | None = None
    product_url: str | None = None
    raw_data: dict | None = None
