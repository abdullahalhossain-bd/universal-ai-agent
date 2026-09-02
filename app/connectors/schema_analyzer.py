from app.connectors.schema_models import (
    DatabaseSchema,
)


class SchemaAnalyzer:

    PRODUCT_HINTS = {
        "product",
        "products",
        "item",
        "items",
        "catalog",
        "inventory",
    }

    NAME_HINTS = {
        "name",
        "product_name",
        "item_name",
        "title",
        "product_title",
    }

    PRICE_HINTS = {
        "price",
        "selling_price",
        "sale_price",
        "amount",
        "cost",
    }

    STOCK_HINTS = {
        "stock",
        "quantity",
        "qty",
        "inventory",
        "available",
    }

    IMAGE_HINTS = {
        "image",
        "image_url",
        "thumbnail",
        "photo",
        "picture",
    }

    def analyze(
        self,
        schema: DatabaseSchema,
    ):

        candidates = []

        for table in schema.tables:

            table_score = 0

            table_name = (
                table.name.lower()
            )

            if any(
                hint in table_name
                for hint in self.PRODUCT_HINTS
            ):

                table_score += 3

            column_names = {
                column.name.lower()
                for column in table.columns
            }

            if column_names & self.NAME_HINTS:

                table_score += 3

            if column_names & self.PRICE_HINTS:

                table_score += 2

            if column_names & self.STOCK_HINTS:

                table_score += 2

            if table_score > 0:

                candidates.append(
                    {
                        "table": table.name,
                        "score": table_score,
                        "columns": list(
                            column_names
                        ),
                    }
                )

        return sorted(
            candidates,
            key=lambda x: x["score"],
            reverse=True,
        )
