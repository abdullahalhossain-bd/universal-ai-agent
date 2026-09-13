from types import SimpleNamespace

from app.products.recommendation import rank_products
from app.search.behavior_learning import EVENT_WEIGHTS, ALLOWED_EVENTS


def product(product_id, name, price):
    return SimpleNamespace(
        id=product_id,
        name=name,
        category="laptop",
        description="",
        price=price,
        stock=10,
        attributes={},
        rating=None,
        review_count=None,
        sales_count=None,
        bestseller_score=None,
    )


def test_observed_behavior_can_change_best_ranking():
    products = [product("a", "Laptop A", 70000), product("b", "Laptop B", 70000)]
    ranked = rank_products(products, "best laptop", behavior_scores={"b": 10.0})
    assert ranked[0].id == "b"


def test_missing_behavior_does_not_create_signal():
    products = [product("a", "Laptop A", 70000), product("b", "Laptop B", 70000)]
    ranked = rank_products(products, "best laptop")
    assert {p.id for p in ranked} == {"a", "b"}


def test_behavior_event_weights_are_explicit():
    assert EVENT_WEIGHTS["impression"] == 0.0
    assert EVENT_WEIGHTS["click"] > 0
    assert EVENT_WEIGHTS["purchase"] > EVENT_WEIGHTS["click"]
    assert "purchase" in ALLOWED_EVENTS
    assert "query_repeat" in ALLOWED_EVENTS
    assert "query_refine" in ALLOWED_EVENTS
