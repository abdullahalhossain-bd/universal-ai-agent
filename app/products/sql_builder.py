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
            if field == "table" or field == "attributes":
                continue
            if column and column not in columns:
                columns.append(column)
        for column in (self.mapping.get("attributes") or {}).values():
            if column and column not in columns:
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
        self._add_dynamic_attribute_filters(conditions, params, request.attributes)

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

    @staticmethod
    def _ordered_expansion(value: str):
        original = str(value).strip()
        if not original:
            return []
        terms = [original]
        seen = {original.casefold()}
        for term in expand_terms([original]):
            normalized = str(term).strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                terms.append(normalized)
                seen.add(key)
        return terms

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
        terms = self._ordered_expansion(str(value))
        clauses = []
        for index, term in enumerate(terms):
            parameter = prefix if index == 0 else f"{prefix}_{index}"
            clauses.append(self.dialect.contains(column, parameter))
            params[parameter] = f"%{term}%"
        if clauses:
            conditions.append("(" + " OR ".join(clauses) + ")")

    def _add_dynamic_attribute_filters(self, conditions, params, attributes):
        """Apply merchant-defined attributes without a platform-wide field list.

        Supported values:
          {"ram": "16GB"}
          {"width": {"value": 6, "op": ">="}}

        The attribute key is safe because it can only resolve to a validated
        datasource column from mapping["attributes"]. Values remain parameters.
        """
        if not attributes:
            return
        mapping = self.mapping.get("attributes") or {}
        allowed_ops = {"=", "!=", ">", ">=", "<", "<="}

        for index, (attribute, raw_value) in enumerate(attributes.items()):
            column = mapping.get(attribute)
            if not column:
                continue
            operator = "="
            value = raw_value
            if isinstance(raw_value, dict):
                value = raw_value.get("value")
                operator = str(raw_value.get("op", "=")).strip()
            if value is None or operator not in allowed_ops:
                continue

            parameter = f"attribute_{index}"
            quoted = self.dialect.quote(column)
            conditions.append(f"{quoted} {operator} :{parameter}")
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
        searchable += list((self.mapping.get("attributes") or {}).values())
        searchable = list(dict.fromkeys(column for column in searchable if column))
        if not searchable:
            return

        terms = [term.strip() for term in str(query_text).split() if term.strip()]
        for index, term in enumerate(terms):
            expanded = self._ordered_expansion(term)
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
