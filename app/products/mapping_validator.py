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

            if field == "attributes":
                if not isinstance(column, dict):
                    raise ValueError("'attributes' mapping must be an object")
                for attribute, definition in column.items():
                    if not isinstance(attribute, str) or not attribute.strip():
                        raise ValueError("Dynamic attribute names must be non-empty strings")
                    if isinstance(definition, dict):
                        attribute_column = definition.get("column")
                        aliases = definition.get("aliases") or []
                        if isinstance(aliases, str):
                            aliases = [aliases]
                        if not isinstance(aliases, list) or any(
                            not isinstance(alias, str) or not alias.strip()
                            for alias in aliases
                        ):
                            raise ValueError(
                                f"Aliases for dynamic attribute '{attribute}' must be strings"
                            )
                    else:
                        attribute_column = definition
                    if not isinstance(attribute_column, str) or not attribute_column.strip():
                        raise ValueError(f"Invalid column for dynamic attribute: {attribute}")
                    validate_identifier(attribute_column)
                continue

            if field not in ALLOWED_PRODUCT_FIELDS:
                raise ValueError(f"Unsupported field: {field}")
            if isinstance(column, dict):
                column = column.get("column")
            validate_identifier(column)

        if not mapping.get("id"):
            raise ValueError("Product ID mapping required")
        if not mapping.get("name"):
            raise ValueError("Product name mapping required")
        return True
