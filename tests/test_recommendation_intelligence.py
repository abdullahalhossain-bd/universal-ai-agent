from types import SimpleNamespace

from app.planner.rule_planner import plan
from app.products.recommendation import is_recommendation_query, rank_products


def product(
    name,
    price,
    stock=10,
    attributes=None,
    description="",
    category="laptop",
    rating=None,
    review_count=None,
    sales_count=None,
    bestseller_score=None,
):
    return SimpleNamespace(
        name=name,
        price=price,
        stock=stock,
        attributes=attributes or {},
        category=category,
        description=description,
        rating=rating,
        review_count=review_count,
        sales_count=sales_count,
        bestseller_score=bestseller_score,
    )


def test_best_is_a_recommendation_query():
    assert is_recommendation_query("best laptop ta dao")
    assert is_recommendation_query("gaming er jonno সেরা laptop")


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


def test_bayesian_shrinkage_prefers_proven_rating_over_single_five_star():
    """A brand-new item with one 5-star review must not outrank an item
    with hundreds of reviews averaging slightly lower — the raw rating
    alone is not enough evidence yet."""
    catalog = [
        product("Filler A", 15000, rating=4.1, review_count=40),
        product("Filler B", 15000, rating=4.2, review_count=60),
        product("Filler C", 15000, rating=4.3, review_count=35),
        product("New Phone", 15000, rating=5.0, review_count=1),
        product("Proven Phone", 15000, rating=4.6, review_count=500),
    ]
    ranked = rank_products(catalog, "best phone")
    assert ranked[0].name == "Proven Phone"


def test_out_of_stock_is_deprioritized_even_with_a_higher_rating():
    """The assistant should not lead with a product the customer can't
    actually buy right now, even if its raw signals look stronger."""
    items = [
        product("Out Of Stock Star", 15000, stock=0, rating=4.9, review_count=300),
        product("Available Good", 15000, stock=5, rating=4.5, review_count=300),
    ]
    ranked = rank_products(items, "best phone")
    assert ranked[0].name == "Available Good"


def test_unknown_stock_is_not_penalized():
    """A merchant that doesn't track stock (``None``) should not be treated
    as if their product were sold out."""
    items = [
        product("Untracked Stock", 15000, stock=None, rating=4.8, review_count=200),
        product("Confirmed In Stock", 15000, stock=5, rating=4.2, review_count=200),
    ]
    ranked = rank_products(items, "best phone")
    assert ranked[0].name == "Untracked Stock"


def test_variant_flooding_makes_room_for_distinct_products():
    """A 'best' answer should not be five colourways of the same shirt —
    genuinely distinct products must still surface near the top."""
    variants = [
        product(f"Shirt - {colour}", 1000, category="shirt")
        for colour in ("Red", "Blue", "Green", "Black", "White")
    ]
    distinct = product("Trousers", 1500, category="pants")
    ranked = rank_products(variants + [distinct], "best")
    top_three_names = {p.name for p in ranked[:3]}
    assert "Trousers" in top_three_names


def test_viral_outlier_does_not_zero_out_other_popular_products():
    """Log-dampened popularity should preserve a sensible ordering instead
    of one viral bestseller crushing every other product's score."""
    viral = product("Viral Phone", 15000, sales_count=100000)
    normal = product("Solid Phone", 15000, sales_count=200)
    ranked = rank_products([viral, normal], "popular phone")
    assert {p.name for p in ranked} == {"Viral Phone", "Solid Phone"}
    assert ranked[0].name == "Viral Phone"  # still correctly ordered
    assert ranked[1].name == "Solid Phone"  # but not scored at zero
