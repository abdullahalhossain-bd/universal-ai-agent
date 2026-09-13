from app.chat.intent_semantics import classify_product_link_request


def test_explicit_link_variations_are_link_intent():
    for query in (
        "ওইটার লিংক",
        "link ta dao",
        "ওটার website",
        "product pageটা দেন",
        "buy link",
        "URL dao",
        "লিঙ্ক দিন",
    ):
        assert classify_product_link_request(query) is True, query


def test_natural_purchase_destination_is_link_intent():
    for query in (
        "কোথা থেকে কিনব?",
        "কোথায় পাব?",
        "where can I buy this?",
        "where do I purchase it",
    ):
        result = classify_product_link_request(query)
        assert result in (True, None), query


def test_generic_product_search_is_not_link_intent():
    for query in (
        "laptop দেখাও",
        "show me laptops",
        "কি কি product আছে",
        "what products do you have",
    ):
        assert classify_product_link_request(query) is False, query


def test_store_location_is_not_product_link_intent():
    for query in (
        "আপনাদের অফিস কোথায়?",
        "where is your office",
        "delivery কোথায়",
    ):
        assert classify_product_link_request(query) is False, query
