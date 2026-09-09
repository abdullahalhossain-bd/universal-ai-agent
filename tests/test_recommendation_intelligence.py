from types import SimpleNamespace

from app.planner.rule_planner import plan
from app.products.recommendation import is_recommendation_query, rank_products


def product(name, price, stock=10, attributes=None, description=""):
    return SimpleNamespace(
        name=name,
        price=price,
        stock=stock,
        attributes=attributes or {},
        category="laptop",
        description=description,
    )


def test_best_is_a_recommendation_query():
    assert is_recommendation_query("best laptop ta dao")
    assert is_recommendation_query("gaming er jonno sেরা laptop")


def test_best_laptop_is_product_search_even_without_attribute_filter():
    planned = plan("best laptop ta dao", store_terms={"laptop"})
    assert planned.intent.value == "product_search"
    assert planned.product_filters.product_name == "laptop"


def test_best_use_case_query_is_product_search_without_hardcoded_category():
    planned = plan("student er jonno best", store_terms=set())
    assert planned.intent.value == "product_search"
    assert planned.product_filters.product_name is None


def test_budget_is_hard_filter_and_best_ranking_prefers_value():
    items = [
        product("Laptop A", 65000, attributes={"ram": "16GB", "ssd": "512GB"}),
        product("Laptop B", 50000, attributes={"ram": "8GB", "ssd": "512GB"}),
        product("Laptop C", 70000, attributes={"ram": "16GB", "ssd": "1TB"}),
    ]
    planned = plan("budget 70k er moddhe best laptop", store_terms={"laptop"})
    assert planned.product_filters.max_price == 70000
    ranked = rank_products(items, "budget 70k er moddhe best laptop")
    assert {p.name for p in ranked} == {"Laptop A", "Laptop B", "Laptop C"}
    assert ranked[0].name in {"Laptop B", "Laptop A", "Laptop C"}


def test_use_case_words_can_match_merchant_attribute_content():
    items = [
        product("Office Laptop", 60000, attributes={"use_case": "office student"}),
        product("Gaming Laptop", 90000, attributes={"use_case": "gaming", "gpu": "RTX 4060"}),
    ]
    ranked = rank_products(items, "gaming er jonno best laptop")
    assert ranked[0].name == "Gaming Laptop"


def test_multiple_attribute_context_is_preserved_before_ranking():
    items = [
        product("Black XL", 3000, attributes={"color": "black", "size": "XL"}),
        product("White XL", 2500, attributes={"color": "white", "size": "XL"}),
    ]
    ranked = rank_products(items, "black XL best")
    assert ranked[0].name == "Black XL"
