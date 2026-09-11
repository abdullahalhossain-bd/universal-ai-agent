from app.planner.models import Intent
from app.planner.rule_planner import plan


class MerchantTerms(set):
    def __init__(self, *terms, attribute_schema=None):
        super().__init__(terms)
        self.attribute_schema = attribute_schema or {}


def test_arbitrary_merchant_entity_is_resolved_without_product_hardcoding():
    terms = MerchantTerms("Aurora X9", "Northstar", "Outdoor Lighting")

    action = plan("show me Aurora X9", terms)

    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.product_name == "aurora x9"


def test_arbitrary_category_or_brand_vocabulary_is_used_as_catalog_entity():
    terms = MerchantTerms("Northstar", "Outdoor Lighting", "Solar Garden Lamp")

    brand_action = plan("Northstar", terms)
    category_action = plan("Outdoor Lighting", terms)

    assert brand_action.intent == Intent.PRODUCT_SEARCH
    assert brand_action.product_filters.product_name == "northstar"
    assert category_action.intent == Intent.PRODUCT_SEARCH
    assert category_action.product_filters.product_name == "outdoor lighting"


def test_merchant_defined_attribute_schema_drives_attribute_extraction():
    terms = MerchantTerms(
        "Aurora X9",
        attribute_schema={
            "material": ["material", "উপাদান"],
            "lumens": ["lumens", "লুমেন"],
        },
    )

    action = plan("Aurora X9 material aluminum", terms)

    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.attributes.get("material") == "aluminum"


def test_existence_word_does_not_become_inventory_filter():
    terms = MerchantTerms("Aurora X9")

    action = plan("Aurora X9 ache", terms)

    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.in_stock is False


def test_explicit_inventory_language_still_enables_stock_filter():
    terms = MerchantTerms("Aurora X9")

    action = plan("Aurora X9 in stock", terms)

    assert action.intent == Intent.PRODUCT_SEARCH
    assert action.product_filters is not None
    assert action.product_filters.in_stock is True
