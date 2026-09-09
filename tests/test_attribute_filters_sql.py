from sqlalchemy import JSON, Column, MetaData, Table, create_engine, insert, select

from app.products.attribute_filters import apply_attribute_filters


def test_structured_attribute_filter_matches_16gb_without_description_search():
    metadata = MetaData()
    products = Table(
        "attribute_products",
        metadata,
        Column("id", primary_key=True),
        Column("attributes", JSON, nullable=False),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            insert(products),
            [
                {"id": 1, "attributes": {"ram": "16GB", "color": "black", "size": "XL"}},
                {"id": 2, "attributes": {"ram": "8 GB", "color": "black", "size": "L"}},
            ],
        )
        query = apply_attribute_filters(
            select(products),
            {"ram": "16GB"},
            products.c.attributes,
        )
        assert [row.id for row in conn.execute(query)] == [1]


def test_multiple_dynamic_attributes_are_anded():
    metadata = MetaData()
    products = Table(
        "attribute_products_multi",
        metadata,
        Column("id", primary_key=True),
        Column("attributes", JSON, nullable=False),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            insert(products),
            [
                {"id": 1, "attributes": {"finish": "black", "size": "XL"}},
                {"id": 2, "attributes": {"finish": "black", "size": "L"}},
                {"id": 3, "attributes": {"finish": "white", "size": "XL"}},
            ],
        )
        query = apply_attribute_filters(
            select(products),
            {"finish": "BLACK", "size": "xl"},
            products.c.attributes,
        )
        assert [row.id for row in conn.execute(query)] == [1]
