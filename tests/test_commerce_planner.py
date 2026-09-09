from app.planner.models import Intent
from app.planner.rule_planner import plan


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
