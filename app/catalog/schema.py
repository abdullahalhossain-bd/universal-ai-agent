from pydantic import BaseModel


class UniversalProduct(BaseModel):

    external_id: str

    sku: str | None = None

    name: str

    description: str | None = None

    price: float | None = None

    compare_at_price: float | None = None

    currency: str = "BDT"

    stock_quantity: int | None = None

    in_stock: bool | None = None

    category: str | None = None

    brand: str | None = None

    image_url: str | None = None

    image_urls: list[str] = []

    product_url: str | None = None

    metadata: dict = {}
