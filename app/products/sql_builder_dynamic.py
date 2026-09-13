from app.products.mapping_validator import MappingValidator
from app.products.query_models import ProductSearchRequest
from app.search.synonyms import expand_terms


class DynamicProductSQLBuilder:
    def __init__(self, mapping: dict, dialect):
        self.mapping = mapping
        self.dialect = dialect
        MappingValidator().validate(mapping)

    @staticmethod
    def _column_definition(definition):
        return definition.get("column") if isinstance(definition, dict) else definition

    def _column(self, field):
        return self._column_definition(self.mapping.get(field))

    def _attributes(self):
        return {
            str(name).strip().lower(): self._column_definition(definition)
            for name, definition in (self.mapping.get("attributes") or {}).items()
            if self._column_definition(definition)
        }

    def build(self, request: ProductSearchRequest):
        table = self.dialect.quote(self.mapping["table"])
        columns = []
        for field, definition in self.mapping.items():
            if field in {"table", "attributes"}:
                continue
            column = self._column_definition(definition)
            if column and column not in columns:
                columns.append(column)
        for definition in (self.mapping.get("attributes") or {}).values():
            column = self._column_definition(definition)
            if column and column not in columns:
                columns.append(column)

        sql = f"SELECT {', '.join(self.dialect.quote(c) for c in columns)} FROM {table}"
        conditions, params = [], {}
        self._exact(conditions, params, request.brand, "brand")
        self._contains(conditions, params, request.category, "category", "category_value")
        self._contains(conditions, params, request.subcategory, "subcategory", "subcategory_value")
        self._exact(conditions, params, request.sku, "sku")
        self._contains(conditions, params, request.color, "color", "color_value")
        self._exact(conditions, params, request.size, "size")
        self._exact(conditions, params, request.material, "material")
        self._price(conditions, params, request.min_price, request.max_price)
        self._dynamic_attributes(conditions, params, request.attributes)

        stock = self._column("stock")
        if request.in_stock_only and stock:
            conditions.append(f"{self.dialect.quote(stock)} > :stock_min")
            params["stock_min"] = 0

        name = self._column("name")
        if request.product_name and name:
            conditions.append(self.dialect.contains(name, "product_name"))
            params["product_name"] = f"%{request.product_name}%"

        if request.query and request.query != request.product_name:
            self._free_text(conditions, params, request.query)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return sql + f" LIMIT {request.limit}", params

    def _exact(self, conditions, params, value, field):
        column = self._column(field)
        if value is None or not column:
            return
        parameter = f"{field}_value"
        conditions.append(self.dialect.equals(column, parameter))
        params[parameter] = str(value).strip()

    def _contains(self, conditions, params, value, field, prefix):
        column = self._column(field)
        if value is None or not column:
            return
        clauses = []
        terms = [str(value).strip()]
        for term in expand_terms(terms):
            if term not in terms:
                terms.append(term)
        for index, term in enumerate(terms):
            parameter = prefix if index == 0 else f"{prefix}_{index}"
            clauses.append(self.dialect.contains(column, parameter))
            params[parameter] = f"%{term}%"
        if clauses:
            conditions.append("(" + " OR ".join(clauses) + ")")

    def _dynamic_attributes(self, conditions, params, attributes):
        if not attributes:
            return
        allowed = {"=", "!=", ">", ">=", "<", "<="}
        mapping = self._attributes()
        for index, (name, raw) in enumerate(attributes.items()):
            column = mapping.get(str(name).strip().lower())
            if not column:
                continue
            op, value = "=", raw
            if isinstance(raw, dict):
                op = str(raw.get("op", "=")).strip()
                value = raw.get("value")
            if value is None or op not in allowed:
                continue
            parameter = f"attribute_{index}"
            conditions.append(f"{self.dialect.quote(column)} {op} :{parameter}")
            params[parameter] = value

    def _price(self, conditions, params, minimum, maximum):
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

    def _free_text(self, conditions, params, query_text):
        columns = [
            self._column(field)
            for field in (
                "name", "description", "brand", "category", "subcategory",
                "tags", "color", "size", "material", "variant", "sku", "barcode",
            )
        ] + list(self._attributes().values())
        columns = list(dict.fromkeys(c for c in columns if c))
        for index, term in enumerate(str(query_text).split()):
            if not term.strip():
                continue
            parameter = f"search_term_{index}"
            conditions.append("(" + " OR ".join(self.dialect.contains(c, parameter) for c in columns) + ")")
            params[parameter] = f"%{term.strip()}%"
