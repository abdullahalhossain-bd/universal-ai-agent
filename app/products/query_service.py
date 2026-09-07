from app.products.query_models import ProductSearchRequest
from app.products.sql_builder import ProductSQLBuilder
from app.products.universal import UniversalProduct


class ProductQueryService:
    def __init__(self, connector, mapping, dialect):
        self.connector = connector
        self.builder = ProductSQLBuilder(mapping=mapping, dialect=dialect)
        self.mapping = mapping

    async def search(self, request: ProductSearchRequest):
        sql, params = self.builder.build(request)
        rows = await self.connector.execute_query(sql, params)
        return [self._normalize(row) for row in rows]

    def _normalize(self, row):
        def get(field):
            entry = self.mapping.get(field)
            if isinstance(entry, dict):
                entry = entry.get("column")
            return row.get(entry) if entry else None

        attributes = get("attributes")
        if not isinstance(attributes, dict):
            attributes = None

        return UniversalProduct(
            id=str(get("id")),
            name=str(get("name") or ""),
            price=get("price"),
            stock=get("stock"),
            sku=get("sku"),
            description=get("description"),
            category=get("category"),
            brand=get("brand"),
            model=get("model"),
            attributes=attributes,
            image_url=get("image"),
            product_url=get("url"),
            raw_data=dict(row),
        )
