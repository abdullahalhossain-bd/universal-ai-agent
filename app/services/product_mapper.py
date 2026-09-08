from decimal import Decimal
from typing import Any

from app.schemas.product import (
    ProductImage,
    UniversalProduct,
)


class ProductMapper:

    def map(
        self,
        row: dict[str, Any],
        mapping: dict[str, str],
    ) -> UniversalProduct:

        def get(
            semantic_type: str,
            default=None,
        ):
            column = mapping.get(
                semantic_type
            )

            if not column:
                return default

            return row.get(column, default)

        images = []

        image_value = get("image")

        if image_value:
            images.append(
                ProductImage(
                    url=str(image_value)
                )
            )

        price = get("price")

        if price is not None:
            price = Decimal(str(price))

        stock = get("stock")

        if stock is not None:
            try:
                stock = int(stock)
            except (ValueError, TypeError):
                stock = None

        return UniversalProduct(
            id=str(
                get("id", "")
            ),
            name=str(
                get("name", "")
            ),
            description=get(
                "description"
            ),
            price=price,
            currency=get(
                "currency"
            ),
            stock=stock,
            sku=get("sku"),
            category=get("category"),
            brand=get("brand"),
            images=images,
            url=get("url"),
            source_metadata={
                "source": "merchant_database"
            },
        )
