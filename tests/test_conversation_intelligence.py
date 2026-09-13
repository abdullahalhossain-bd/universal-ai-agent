from app.chat.conversation_intelligence import extract_product_index, resolve_follow_up


PRODUCTS = [
    {"id": "p1", "name": "HP Intel i5"},
    {"id": "p2", "name": "Dell Intel i7"},
    {"id": "p3", "name": "Asus Gaming"},
]


def test_extract_product_index_supports_english_and_bangla_ordinals():
    assert extract_product_index("2nd tar link dao") == 2
    assert extract_product_index("second one er price") == 2
    assert extract_product_index("তৃতীয়টার দাম কত") == 3
    assert extract_product_index("৪ নম্বরটা দেখাও") == 4


def test_link_follow_up_resolves_selected_product():
    result = resolve_follow_up("2nd tar link dao", PRODUCTS)
    assert result.is_follow_up
    assert result.action == "product_link"
    assert result.product_index == 2
    assert result.product_ids == ("p2",)


def test_price_and_image_followups_work_with_deictic_reference():
    assert resolve_follow_up("etar dam koto?", [{"id": "p1"}]).action == "product_price"
    assert resolve_follow_up("ওইটার ছবি দাও", [{"id": "p1"}]).action == "product_image"


def test_compare_follow_up_keeps_all_previous_products():
    result = resolve_follow_up("egula compare koro", PRODUCTS)
    assert result.is_follow_up
    assert result.action == "compare_products"
    assert result.product_ids == ("p1", "p2", "p3")


def test_multiple_products_do_not_guess_bare_deictic_reference():
    result = resolve_follow_up("eta", PRODUCTS)
    assert not result.is_follow_up
    assert result.action is None


def test_unknown_followup_is_left_for_normal_planner():
    result = resolve_follow_up("thanks", PRODUCTS)
    assert not result.is_follow_up
    assert result.action is None


def test_product_selection_can_be_resolved_without_action_word():
    result = resolve_follow_up("third one", PRODUCTS)
    assert result.action == "select_product"
    assert result.product_ids == ("p3",)
