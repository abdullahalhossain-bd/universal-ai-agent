from app.products.mapping_validator import MappingValidator
from app.products.query_models import ProductSearchRequest


class ProductSQLBuilder:
    def __init__(self, mapping: dict, dialect):
        self.mapping = mapping
        self.dialect = dialect
        MappingValidator().validate(mapping)

    def build(self, request: ProductSearchRequest):
        table = self.dialect.quote(self.mapping["table"])

        # Select every mapped canonical field so datasource mapping is not merely
        # cosmetic; unmapped source columns remain available through raw_data.
        columns = []
        for field, column in self.mapping.items():
            if field != "table" and column and column not in columns:
                columns.append(column)

        select_sql = ", ".join(self.dialect.quote(column) for column in columns)
        sql = f"SELECT {select_sql} FROM {table}"
        conditions = []
        params = {}

        self._add_equal_filter(conditions, params, request.brand, "brand")
        self._add_equal_filter(conditions, params, request.category, "category")
        self._add_equal_filter(conditions, params, request.sku, "sku")
        self._add_price_filter(conditions, params, request.min_price, request.max_price)

        if request.in_stock_only and self.mapping.get("stock"):
            conditions.append(f'{self.dialect.quote(self.mapping["stock"])} > :stock_min')
            params["stock_min"] = 0

        if request.product_name:
            name_column = self.mapping["name"]
            conditions.append(self.dialect.contains(name_column, "product_name"))
            params["product_name"] = f"%{request.product_name}%"

        # Only use the generic query when product_name is not already carrying
        # the same text; this prevents accidental double filtering.
        if request.query and request.query != request.product_name:
            self._add_free_text_conditions(conditions, params, request.query)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        return sql + f" LIMIT {request.limit}", params

    def _add_free_text_conditions(self, conditions, params, query_text):
        if not query_text:
            return

        searchable = [
            self.mapping.get(field)
            for field in (
                "name", "description", "brand", "category", "subcategory",
                "tags", "color", "size", "material", "variant", "sku", "barcode",
            )
        ]
        searchable = list(dict.fromkeys(column for column in searchable if column))
        if not searchable:
            return

        terms = [term.strip() for term in str(query_text).split() if term.strip()]
        for index, term in enumerate(terms):
            parameter = f"search_term_{index}"
            per_column = [self.dialect.contains(column, parameter) for column in searchable]
            conditions.append("(" + " OR ".join(per_column) + ")")
            params[parameter] = f"%{term}%"

    def _add_equal_filter(self, conditions, params, value, field):
        if value is None or not self.mapping.get(field):
            return
        parameter = f"{field}_value"
        conditions.append(f'{self.dialect.quote(self.mapping[field])} = :{parameter}')
        params[parameter] = value

    def _add_price_filter(self, conditions, params, minimum, maximum):
        column = self.mapping.get("price")
        if not column:
            return
        quoted = self.dialect.quote(column)
        if minimum is not None:
            conditions.append(f"{quoted} >= :min_price")
            params["min_price"] = minimum
        if maximum is not None:
            conditions.append(f"{quoted} <= :max_price")
            params["max_price"] = maximum
