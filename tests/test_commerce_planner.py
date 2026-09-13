from app.chat.dynamic_service import DynamicAttributeChatService
from app.chat.professional_service import ProfessionalCommerceChatService
from app.planner.models import Intent, ProductFilters
from app.planner.rule_planner import plan
from app.products.recommendation import is_recommendation_query
from app.products.semantic_attributes import deterministic_extract
from app.chat.intelligent_service import IntelligentCommerceChatService


STORE_TERMS = {"Iphone12", "Laptop", "Asus Gaming", "Dell Intel i9"}


def test_phone_existence_resolves_to_iphone_product_without_stock_filter():
    for query in ("I phone ase?", "Phone ase?", "Iphone ase?", "ফোন আছে?"):
        action = plan(query, STORE_TERMS)
        assert action.intent == Intent.PRODUCT_SEARCH
        assert action.product_filters is not None
        assert action.product_filters.in_stock is False
        assert action.product_filters.product_name == "iphone12"


def test_product_existence_queries_do_not_force_in_stock_filter():
    for query in ("laptop ase", "laptop ache", "ল্যাপটপ আছে", "laptop available"):
        action = plan(query, {"Laptop"})
        assert action.intent == Intent.PRODUCT_SEARCH
        assert action.product_filters is not None
        assert action.product_filters.in_stock is ("available" in query.casefold())
        assert action.product_filters.product_name == "laptop"


def test_explicit_inventory_queries_set_in_stock():
    for query in ("laptop in stock", "laptop stock ache", "available laptop", "স্টকে laptop"):
        action = plan(query, {"Laptop"})
        assert action.intent == Intent.PRODUCT_SEARCH
        assert action.product_filters is not None
        assert action.product_filters.in_stock is True


def test_existence_query_is_not_mistaken_for_recommendation():
    for query in ("laptop ase", "laptop ache", "ল্যাপটপ আছে", "phone available"):
        assert not is_recommendation_query(query)


def test_knowledge_question_is_not_forced_into_product_search_or_mixed():
    for query in (
        "What is your return policy?",
        "What is the return policy?",
        "Can you tell me your shipping policy?",
        "return policy",
        "shipping policy",
    ):
        action = plan(query, STORE_TERMS)
        assert action.intent == Intent.KNOWLEDGE_SEARCH


def test_catalog_browse_remains_catalog_browse():
    for query in ("what do you have", "what do you sell", "what's available", "কি কি আছে"):
        action = plan(query, STORE_TERMS)
        assert action.intent == Intent.CATALOG_BROWSE


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


def test_professional_product_index_reference_supports_bengali_ordinals():
    service = ProfessionalCommerceChatService.__new__(ProfessionalCommerceChatService)
    assert service._extract_product_index("২ নম্বরটার দাম কত?") == 2
    assert service._extract_product_index("second one er link dao") == 2
    assert service._extract_product_index("তৃতীয়টা দেখাও") == 3
    assert service._extract_product_index("চতুর্থটার link dao") == 4
    assert service._extract_product_index("পঞ্চমটার ছবি দাও") == 5


def test_recommendation_support_requires_meaningful_evidence():
    weak = {"name": "Laptop", "rating": 4.7, "review_count": 1, "sales_count": 0, "bestseller_score": 0}
    assert not ProfessionalCommerceChatService._recommendation_has_support([weak])
    assert ProfessionalCommerceChatService._recommendation_has_support([
        {"name": "Laptop", "rating": 4.7, "review_count": 12, "sales_count": 0, "bestseller_score": 0}
    ])
    assert ProfessionalCommerceChatService._recommendation_has_support([
        {"name": "Laptop", "rating": None, "review_count": None, "sales_count": 20, "bestseller_score": 0}
    ])


def test_dynamic_recommendation_evidence_requires_meaningful_catalog_signals():
    class ProductStub:
        rating = None
        review_count = None
        sales_count = None
        bestseller_score = None

    assert not DynamicAttributeChatService._recommendation_evidence([ProductStub()])
    ProductStub.rating = 3.9
    ProductStub.review_count = 100
    assert not DynamicAttributeChatService._recommendation_evidence([ProductStub()])
    ProductStub.rating = 4.7
    ProductStub.review_count = 5
    assert DynamicAttributeChatService._recommendation_evidence([ProductStub()])


def test_generic_product_search_does_not_require_store_vocabulary():
    for query in ("Nike shoes", "কালো জুতা দেখাও চাই", "laptop"):
        action = plan(query, None)
        assert action.intent == Intent.PRODUCT_SEARCH
        assert action.product_filters is not None


def test_dynamic_continuation_is_not_a_confirmation_phrase_allowlist():
    class DBStub:
        def query(self, model): return self
        def filter(self, *args, **kwargs): return self
        def first(self): return None

    service = DynamicAttributeChatService.__new__(DynamicAttributeChatService)
    service.db = DBStub()
    assert not service._message_has_product_match("store-1", "assa dao")
    assert not service._message_has_product_match("store-1", "accha, kore dao")
    assert not service._message_has_product_match("store-1", "okay please")


def test_dynamic_attributes_use_adjacent_value_not_next_attribute():
    schema = {"ram": ["ram"], "color": ["color"], "size": ["size"]}
    extracted = deterministic_extract("16GB RAM black color XL size", schema)
    assert extracted == {"ram": "16gb", "color": "black", "size": "xl"}


def test_dynamic_attribute_schema_supports_aliases():
    schema = {"finish": ["finish", "color", "colour"], "memory": ["memory", "ram"]}
    extracted = deterministic_extract("black colour 16GB RAM", schema)
    assert extracted["finish"] == "black"
    assert extracted["memory"] == "16gb"


def test_conversation_filter_merge_preserves_previous_constraints_and_current_overrides():
    previous = {
        "product_name": "laptop",
        "min_price": None,
        "max_price": 80000,
        "in_stock": False,
        "recommendation": False,
        "attributes": {"color": "black", "ram": "8gb"},
    }
    current = ProductFilters(attributes={"color": "blue"})
    merged = IntelligentCommerceChatService._merge_filters(previous, current)
    assert merged["product_name"] == "laptop"
    assert merged["max_price"] == 80000
    assert merged["attributes"] == {"color": "blue", "ram": "8gb"}


def test_conversation_filter_merge_is_schema_neutral():
    previous = {
        "product_name": "chair",
        "min_price": None,
        "max_price": None,
        "in_stock": False,
        "recommendation": False,
        "attributes": {"fabric": "linen", "capacity": "4"},
    }
    current = ProductFilters(attributes={"finish": "oak"})
    merged = IntelligentCommerceChatService._merge_filters(previous, current)
    assert merged["attributes"] == {"fabric": "linen", "capacity": "4", "finish": "oak"}
