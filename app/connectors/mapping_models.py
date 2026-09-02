from pydantic import BaseModel


class ProductMapping(BaseModel):

    table: str

    id_column: str

    name_column: str

    price_column: str | None = None

    stock_column: str | None = None

    sku_column: str | None = None

    description_column: str | None = None

    image_column: str | None = None

    url_column: str | None = None
