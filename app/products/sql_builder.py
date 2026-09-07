from app.products.mapping_validator import MappingValidator
from app.products.query_models import ProductSearchRequest


class ProductSQLBuilder:
    """Build safe, parameterized product queries from a connector mapping.

    Free-text search is deliberately generic: every term must match at least
    one useful mapped product field, while different terms are ANDed together.
    This makes "brand category model" queries behave as a combined query
    instead of three independent OR searches.
    """

    # Fields that are useful for free-text product discovery. The mapping is
    # the source of truth; fields absent from a merchant mapping are ignored.
    SEARCH_FIELDS = (
        "name",
        "description",
        "category",
        "brand",
        "sku",
        "model",
        "attributes",
    )

    def __init__(self, mapping: dict, dialect):
        self.mapping = mapping
        self.dialect = dialect
        MappingValidator().validate(mapping)

    def _column(self, field: str):
        value = self.mapping.get(field)
        if isinstance(value, dict):
            return value.get("column")
        return value

    def _search_columns(self):
        columns = []
        for field in self.SEARCH_FIELDS:
            column = self._column(field)
            if column and column not in columns:
                columns.append(column)
        return columns

    def build(self, request: ProductSearchRequest):
        table = self.dialect.quote(self.mapping["table"])

        fields = [
            "id", "name", "price", "stock", "sku", "description",
            "image", "url", "brand", "category", "model", "attributes",
        ]
        columns = []
        for field in fields:
            column = self._column(field)
            if column and column not in columns:
                columns.append(column)

        # id/name are required by MappingValidator, so these are guaranteed.
        select_sql = ", ".join(self.dialect.quote(column) for column in columns)
        sql = f"SELECT {select_sql} FROM {table}"
        conditions = []
        params = {}

        self._add_equal_filter(conditions, params, request.brand, "brand")
        self._add_equal_filter(conditions, params, request.category, "category")
        self._add_equal_filter(conditions, params, request.model, "model")
        self._add_equal_filter(conditions, params, request.sku, "sku")
        self._add_price_filter(
            conditions, params, request.min_price, request.max_price
        )

        if request.in_stock_only:
            stock_column = self._column("stock")
            if stock_column:
                conditions.append(
                    f'{self.dialect.quote(stock_column)} > :stock_min'
                )
                params["stock_min"] = 0

        # Legacy product_name and the newer query field both feed the same
        # generic multi-field matcher. Empty/conversational text is ignored.
        text = request.query or request.product_name or ""
        terms = [
            token.strip(".,!?;:()[]{}\"'")
            for token in str(text).split()
        ]
        terms = [token for token in terms if len(token) >= 2]

        search_columns = self._search_columns()
        for index, term in enumerate(terms):
            if not search_columns:
                break
            term_conditions = []
            parameter = f"search_term_{index}"
            params[parameter] = f"%{term}%"
            for column in search_columns:
                term_conditions.append(
                    self.dialect.contains(column, parameter)
                )
            conditions.append("(" + " OR ".join(term_conditions) + ")")

        if request.attributes and self._column("attributes"):
            # Keep connector-specific attribute filtering parameterized. The
            # exact JSON syntax is dialect-specific, so free-text matching is
            # used as a portable fallback for scalar attribute values.
            attributes_column = self._column("attributes")
            for index, value in enumerate(request.attributes.values()):
                if value is None:
                    continue
                parameter = f"attribute_{index}"
                params[parameter] = f"%{value}%"
                conditions.append(
                    self.dialect.contains(attributes_column, parameter)
                )

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += f" LIMIT {request.limit}"
        return sql, params

    def _add_equal_filter(self, conditions, params, value, field):
        if value is None:
            return
        column = self._column(field)
        if not column:
            return
        parameter = f"{field}_value"
        conditions.append(
            f'{self.dialect.quote(column)} = :{parameter}'
        )
        params[parameter] = value

    def _add_price_filter(self, conditions, params, minimum, maximum):
        column = self._column("price")
        if not column:
            return
        quoted = self.dialect.quote(column)
        if minimum is not None:
            conditions.append(f"{quoted} >= :min_price")
            params["min_price"] = minimum
        if maximum is not None:
            conditions.append(f"{quoted} <= :max_price")
            params["max_price"] = maximum
