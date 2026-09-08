from app.products.fields import (
    ALLOWED_PRODUCT_FIELDS,
)

from app.products.sql_identifier import (
    validate_identifier,
)


class MappingValidator:

    def validate(
        self,
        mapping: dict,
    ):

        if not mapping.get("table"):
            raise ValueError(
                "Product table is required"
            )

        validate_identifier(
            mapping["table"]
        )

        for field, column in mapping.items():

            if field == "table":
                continue

            if (
                field
                not in ALLOWED_PRODUCT_FIELDS
            ):
                raise ValueError(
                    f"Unsupported field: {field}"
                )

            validate_identifier(
                column
            )

        if not mapping.get("id"):
            raise ValueError(
                "Product ID mapping required"
            )

        if not mapping.get("name"):
            raise ValueError(
                "Product name mapping required"
            )

        return True
