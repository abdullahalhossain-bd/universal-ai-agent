from app.planner.models import Intent
from app.planner.rule_planner import plan
from app.chat.dynamic_service import DynamicAttributeChatService


STORE_TERMS = {"Iphone12", "Laptop", "Asus Gaming", "Dell Intel i9"}


def test_phone_existence_resolves_to_iphone_product():
    for query in ("I phone ase?", "Phone ase?", "Iphone ase?", "ফোন আছে?"):
        action = plan(query, STORE_TERMS)
        assert action.intent == Intent.PRODUCT_SEARCH
        assert action.product_filters is not None
        assert action.product_filters.in_stock is True
        assert action.product_filters.product_name == "iphone12"


def test_best_laptop_is_marked_as_recommendation_search():
    action = plan("best laptop konta", STORE_TERMS)
    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.recommendation is True
    assert action.product_filters.product_name == "laptop"


def test_bare_best_keeps_recommendation_mode_without_fake_product():
    action = plan("best konta", STORE_TERMS)
    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.recommendation is True
    assert action.product_filters.product_name is None


def test_catalog_browse_remains_catalog_browse():
    action = plan("what do you have", STORE_TERMS)
    assert action.intent == Intent.CATALOG_BROWSE


def test_bare_recommendation_detector_is_strict():
    assert DynamicAttributeChatService._is_bare_recommendation("best konta")
    assert DynamicAttributeChatService._is_bare_recommendation("best")
    assert not DynamicAttributeChatService._is_bare_recommendation("best laptop")
    assert not DynamicAttributeChatService._is_bare_recommendation("laptop er best konta")


def test_product_follow_up_detectors_cover_bangla_banglish_and_english():
    assert DynamicAttributeChatService._is_link_request("assa link dao laptop tar")
    assert DynamicAttributeChatService._is_link_request("product page dao")
    assert DynamicAttributeChatService._is_image_request("laptop tar image dao")
    assert DynamicAttributeChatService._is_image_request("ওইটার ছবি দাও")
    assert DynamicAttributeChatService._is_recommendation_explanation("kemne sera?")
    assert DynamicAttributeChatService._is_recommendation_explanation("কেন সেরা?")


def test_recommendation_evidence_requires_verified_catalog_signals():
    class ProductStub:
        rating = None
        review_count = None
        sales_count = None
        bestseller_score = None

    assert not DynamicAttributeChatService._recommendation_evidence([ProductStub()])

    ProductStub.rating = 4.7
    assert DynamicAttributeChatService._recommendation_evidence([ProductStub()])
