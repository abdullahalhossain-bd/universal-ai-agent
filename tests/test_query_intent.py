from app.search.query_intent import extract_product_intent
from app.search.product_search import ProductSearchProvider


def test_bangla_mixed_query_becomes_structured_filters():
    result = extract_product_intent("Nike er black shoe ache?")

    assert result["brand"] == "Nike"
    assert result["category"] == "shoe"
    assert result["color"] == "black"
    assert result["in_stock_only"] is True
    assert result["product_name"] is None


def test_price_query_extracts_max_price():
    result = extract_product_intent("কালো Nike জুতা ৩০০০ টাকার মধ্যে দেখাও")

    assert result["brand"] == "Nike"
    assert result["category"] == "shoe"
    assert result["color"] == "black"
    assert result["max_price"] == 3000
    assert result["product_name"] is None


def test_provider_does_not_send_full_natural_language_as_product_name():
    provider = ProductSearchProvider(product_service=None)
    request = provider._build_request("Nike er black shoe ache?", 10)

    assert request.product_name is None
    assert request.brand == "Nike"
    assert request.category == "shoe"
    assert request.color == "black"
    assert request.in_stock_only is True


def test_nested_planner_filters_are_not_discarded():
    class Action:
        def model_dump(self, exclude_none=True):
            return {
                "type": "product_search",
                "query": None,
                "filters": {
                    "brand": "Nike",
                    "category": "shoe",
                    "color": "black",
                    "max_price": 3000,
                },
            }

    provider = ProductSearchProvider(product_service=None)
    request = provider._build_request(Action(), 10)

    assert request.brand == "Nike"
    assert request.category == "shoe"
    assert request.color == "black"
    assert request.max_price == 3000
