from dataclasses import dataclass, field


@dataclass
class UniversalProduct:
    id: str
    name: str
    price: float | None = None
    stock: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    currency: str | None = None
    availability: str | bool | None = None
    tags: str | list | None = None
    color: str | None = None
    size: str | None = None
    material: str | None = None
    variant: str | None = None
    weight: float | None = None
    rating: float | None = None
    review_count: int | None = None
    discount: float | None = None
    compare_at_price: float | None = None
    images: str | list | None = None
    created_at: object | None = None
    updated_at: object | None = None
    # Arbitrary merchant-defined product attributes, preserved end-to-end.
    attributes: dict = field(default_factory=dict)
    raw_data: dict | None = None
