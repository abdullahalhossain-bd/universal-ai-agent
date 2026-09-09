from app.products.fields import ALLOWED_PRODUCT_FIELDS
from app.products.sql_identifier import validate_identifier


class MappingValidator:
    def validate(self, mapping: dict):
        if not mapping.get("table"):
            raise ValueError("Product table is required")
        validate_identifier(mapping["table"])

        for field, column in mapping.items():
            if field == "table":
                continue

            # Dynamic merchant attributes are declared as:
            # {"attributes": {"ram": "ram_column", "warranty": "warranty_column"}}
            if field == "attributes":
                if not isinstance(column, dict):
                    raise ValueError("'attributes' mapping must be an object")
                for attribute, attribute_column in column.items():
                    if not isinstance(attribute, str) or not attribute.strip():
                        raise ValueError("Dynamic attribute names must be non-empty strings")
                    if not isinstance(attribute_column, str) or not attribute_column.strip():
                        raise ValueError(f"Invalid column for dynamic attribute: {attribute}")
                    validate_identifier(attribute_column)
                continue

            if field not in ALLOWED_PRODUCT_FIELDS:
                raise ValueError(f"Unsupported field: {field}")
            validate_identifier(column)

        if not mapping.get("id"):
            raise ValueError("Product ID mapping required")
        if not mapping.get("name"):
            raise ValueError("Product name mapping required")
        return True
