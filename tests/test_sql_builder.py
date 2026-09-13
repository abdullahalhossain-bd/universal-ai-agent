from app.products.query_models import (
    ProductSearchRequest,
)

from app.products.sql_builder import (
    ProductSQLBuilder,
)

from app.products.dialect import (
    MySQLDialect,
)


def test_safe_product_query():

    mapping = {
        "table": "products",
        "id": "product_id",
        "name": "product_name",
        "price": "selling_price",
        "stock": "quantity",
        "brand": "brand",
        "image": "image_url",
    }

    builder = ProductSQLBuilder(
        mapping,
        MySQLDialect(),
    )

    request = ProductSearchRequest(
        brand="Nike",
        max_price=5000,
        in_stock_only=True,
        limit=10,
    )

    sql, params = builder.build(
        request
    )

    assert "DROP" not in sql

    assert ":max_price" in sql

    assert ":stock_min" in sql

    assert params[
        "max_price"
    ] == 5000

    assert params[
        "brand_value"
    ] == "Nike"
