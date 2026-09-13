from app.catalog.schema import (
    UniversalProduct,
)


class ProductAdapter:

    def __init__(
        self,
        mapping: dict,
    ):

        self.mapping = mapping

    def adapt(
        self,
        row: dict,
    ):

        def get(field):

            source = self.mapping.get(
                field
            )

            if not source:
                return None

            return row.get(source)

        return UniversalProduct(
            external_id=str(
                get("external_id")
            ),

            sku=get("sku"),

            name=str(
                get("name") or ""
            ),

            description=get(
                "description"
            ),

            price=self._float(
                get("price")
            ),

            stock_quantity=self._int(
                get("stock_quantity")
            ),

            category=get("category"),

            brand=get("brand"),

            image_url=get("image_url"),

            product_url=get(
                "product_url"
            ),
        )

    def _float(self, value):

        if value is None:
            return None

        return float(value)

    def _int(self, value):

        if value is None:
            return None

        return int(value)
