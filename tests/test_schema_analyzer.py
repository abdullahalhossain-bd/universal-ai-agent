from app.connectors.schema_models import (
    DatabaseSchema,
    TableInfo,
    ColumnInfo,
)

from app.connectors.schema_analyzer import (
    SchemaAnalyzer,
)


def test_product_table_detection():

    schema = DatabaseSchema(
        database_type="mysql",
        tables=[
            TableInfo(
                name="products",
                columns=[
                    ColumnInfo(
                        name="product_id",
                        data_type="varchar",
                    ),
                    ColumnInfo(
                        name="product_name",
                        data_type="varchar",
                    ),
                    ColumnInfo(
                        name="price",
                        data_type="decimal",
                    ),
                    ColumnInfo(
                        name="stock",
                        data_type="int",
                    ),
                ],
            )
        ],
    )

    analyzer = SchemaAnalyzer()

    result = analyzer.analyze(
        schema
    )

    assert len(result) == 1

    assert (
        result[0]["table"]
        == "products"
    )

    assert result[0]["score"] > 0
