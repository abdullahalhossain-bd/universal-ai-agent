from app.products.mapping_validator import MappingValidator
from app.products.query_models import ProductSearchRequest
from app.search.synonyms import expand_terms


class ProductSQLBuilder:
    def __init__(self, mapping: dict, dialect):
        self.mapping = mapping
        self.dialect = dialect
        MappingValidator().validate(mapping)

    def build(self, request: ProductSearchRequest):
        table = self.dialect.quote(self.mapping["table"])
        columns = []
        for field, column in self.mapping.items():
            if field != "table" and column and column not in columns:
                columns.append(column)

        select_sql = ", ".join(self.dialect.quote(column) for column in columns)
        sql = f"SELECT {select_sql} FROM {table}"
        conditions = []
        params = {}

        self._add_exact_filter(conditions, params, request.brand, "brand")
        self._add_synonym_filter(conditions, params, request.category, "category", "category_value")
        self._add_synonym_filter(conditions, params, request.subcategory, "subcategory", "subcategory_value")
        self._add_exact_filter(conditions, params, request.sku, "sku")
        self._add_synonym_filter(conditions, params, request.color, "color", "color_value")
        self._add_exact_filter(conditions, params, request.size, "size")
        self._add_exact_filter(conditions, params, request.material, "material")
        self._add_price_filter(conditions, params, request.min_price, request.max_price)

        if request.in_stock_only and self.mapping.get("stock"):
            conditions.append(f'{self.dialect.quote(self.mapping["stock"])} > :stock_min')
            params["stock_min"] = 0

        if request.product_name and self.mapping.get("name"):
            conditions.append(self.dialect.contains(self.mapping["name"], "product_name"))
            params["product_name"] = f"%{request.product_name}%"

        if request.query and request.query != request.product_name:
            self._add_free_text_conditions(conditions, params, request.query)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return sql + f" LIMIT {request.limit}", params

    def _add_exact_filter(self, conditions, params, value, field):
        column = self.mapping.get(field)
        if value is None or not column:
            return
        parameter = f"{field}_value"
        conditions.append(self.dialect.equals(column, parameter))
        params[parameter] = str(value).strip()

    def _add_synonym_filter(self, conditions, params, value, field, prefix):
        column = self.mapping.get(field)
        if value is None or not column:
            return
        terms = expand_terms([str(value)])
        clauses = []
        for index, term in enumerate(terms):
            parameter = f"{prefix}_{index}"
            clauses.append(self.dialect.contains(column, parameter))
            params[parameter] = f"%{term}%"
        if clauses:
            conditions.append("(" + " OR ".join(clauses) + ")")

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
            expanded = expand_terms([term])
            parameter_clauses = []
            for synonym_index, synonym in enumerate(expanded):
                parameter = (
                    f"search_term_{index}"
                    if synonym_index == 0
                    else f"search_term_{index}_{synonym_index}"
                )
                per_column = [self.dialect.contains(column, parameter) for column in searchable]
                parameter_clauses.append("(" + " OR ".join(per_column) + ")")
                params[parameter] = f"%{synonym}%"
            if parameter_clauses:
                conditions.append("(" + " OR ".join(parameter_clauses) + ")")
