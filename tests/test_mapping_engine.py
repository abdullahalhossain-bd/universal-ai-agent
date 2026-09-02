from app.connectors.mapping_engine import (
    MappingEngine,
)


def test_mapping():

    engine = MappingEngine()

    result = engine.suggest(
        [
            "item_ref",
            "item_title",
            "sell_amt",
            "available_qty",
            "pic",
        ]
    )

    mapping = {
        item.field: item.column
        for item in result
    }

    assert (
        mapping["id"]
        == "item_ref"
    )

    assert (
        mapping["name"]
        == "item_title"
    )

    assert (
        mapping["price"]
        == "sell_amt"
    )

    assert (
        mapping["stock"]
        == "available_qty"
    )

    assert (
        mapping["image"]
        == "pic"
    )
