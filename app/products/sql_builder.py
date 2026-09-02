from app.products.mapping_validator import (
    MappingValidator,
)

from app.products.query_models import (
    ProductSearchRequest,
)


class ProductSQLBuilder:

    def __init__(
        self,
        mapping: dict,
        dialect,
    ):

        self.mapping = mapping
        self.dialect = dialect

        MappingValidator().validate(
            mapping
        )

    def build(
        self,
        request: ProductSearchRequest,
    ):

        table = self.dialect.quote(
            self.mapping["table"]
        )

        columns = [
            self.mapping["id"],
            self.mapping["name"],
        ]

        optional_fields = [
            "price",
            "stock",
            "sku",
            "description",
            "image",
            "url",
            "brand",
            "category",
        ]

        for field in optional_fields:

            if self.mapping.get(field):

                columns.append(
                    self.mapping[field]
                )

        # Remove duplicates
        columns = list(
            dict.fromkeys(columns)
        )

        select_sql = ", ".join(
            self.dialect.quote(column)
            for column in columns
        )

        sql = (
            f'SELECT {select_sql} '
            f'FROM {table}'
        )

        conditions = []

        params = {}

        self._add_equal_filter(
            conditions,
            params,
            request.brand,
            "brand",
        )

        self._add_equal_filter(
            conditions,
            params,
            request.category,
            "category",
        )

        self._add_equal_filter(
            conditions,
            params,
            request.sku,
            "sku",
        )

        self._add_price_filter(
            conditions,
            params,
            request.min_price,
            request.max_price,
        )

        if request.in_stock_only:

            stock_column = self.mapping.get(
                "stock"
            )

            if stock_column:

                conditions.append(
                    f'{self.dialect.quote(stock_column)} > :stock_min'
                )

                params["stock_min"] = 0

        if request.product_name:

            name_column = self.mapping[
                "name"
            ]

            conditions.append(
                self.dialect.contains(
                    name_column,
                    "product_name",
                )
            )

            params["product_name"] = (
                f"%{request.product_name}%"
            )

        if conditions:

            sql += (
                " WHERE "
                + " AND ".join(
                    conditions
                )
            )

        sql += (
            f' LIMIT {request.limit}'
        )

        return sql, params

    def _add_equal_filter(
        self,
        conditions,
        params,
        value,
        field,
    ):

        if value is None:
            return

        column = self.mapping.get(
            field
        )

        if not column:
            return

        parameter = f"{field}_value"

        conditions.append(
            f'{self.dialect.quote(column)} = :{parameter}'
        )

        params[parameter] = value

    def _add_price_filter(
        self,
        conditions,
        params,
        minimum,
        maximum,
    ):

        column = self.mapping.get(
            "price"
        )

        if not column:
            return

        quoted = self.dialect.quote(
            column
        )

        if minimum is not None:

            conditions.append(
                f'{quoted} >= :min_price'
            )

            params["min_price"] = minimum

        if maximum is not None:

            conditions.append(
                f'{quoted} <= :max_price'
            )

            params["max_price"] = maximum
