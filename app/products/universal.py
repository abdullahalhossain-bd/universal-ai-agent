from dataclasses import dataclass


@dataclass
class UniversalProduct:

    id: str

    name: str

    price: float | None = None

    stock: int | None = None

    sku: str | None = None

    description: str | None = None

    image_url: str | None = None

    product_url: str | None = None

    raw_data: dict | None = None
