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
            column = self.mapping.get(field)
            return row.get(column) if column else None

        attributes = {}
        for semantic_name, column in (self.mapping.get("attributes") or {}).items():
            value = row.get(column)
            if value is not None:
                attributes[semantic_name] = value

        return UniversalProduct(
            id=str(get("id")),
            name=str(get("name")),
            price=get("price"),
            stock=get("stock"),
            sku=get("sku"),
            barcode=get("barcode"),
            description=get("description"),
            image_url=get("image"),
            product_url=get("url"),
            brand=get("brand"),
            category=get("category"),
            subcategory=get("subcategory"),
            currency=get("currency"),
            availability=get("availability"),
            tags=get("tags"),
            color=get("color"),
            size=get("size"),
            material=get("material"),
            variant=get("variant"),
            weight=get("weight"),
            rating=get("rating"),
            review_count=get("review_count"),
            discount=get("discount"),
            compare_at_price=get("compare_at_price"),
            images=get("images"),
            created_at=get("created_at"),
            updated_at=get("updated_at"),
            attributes=attributes,
            raw_data=dict(row),
        )
