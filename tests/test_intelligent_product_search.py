import pytest

from app.planner.rule_planner import plan
from app.planner.models import Intent
from app.planner.service import QueryPlanner
from app.search.synonyms import expand_terms
from app.products.query_models import ProductSearchRequest
from app.products.sql_builder import ProductSQLBuilder
from app.products.dialect import MySQLDialect


def test_arbitrary_product_name_is_product_intent():
    result = plan("Acme X200")
    assert result.intent == Intent.PRODUCT_SEARCH
    assert result.product_filters.product_name == "Acme X200"


def test_bengali_conversational_words_are_removed():
    result = plan("কালো জুতা দেখাও চাই")
    assert result.intent == Intent.PRODUCT_SEARCH
    assert "দেখাও" not in result.product_filters.product_name
    assert "চাই" not in result.product_filters.product_name


def test_mixed_query_keeps_terms_and_price_filter():
    result = plan("Nike shoes ৫০০০ টাকার মধ্যে")
    assert result.intent == Intent.PRODUCT_SEARCH
    assert result.product_filters.max_price == 5000
    assert "Nike" in result.product_filters.product_name
    assert "shoes" in result.product_filters.product_name


def test_synonym_expansion_handles_bengali_and_english():
    expanded = {term.lower() for term in expand_terms(["জুতা"])}
    assert "shoe" in expanded
    assert "shoes" in expanded


def test_synonym_expansion_handles_common_typo():
    expanded = {term.lower() for term in expand_terms(["laptpo"])}
    assert "laptop" in expanded


def test_sql_requires_all_terms_but_allows_any_search_field():
    mapping = {
        "table": "products", "id": "id", "name": "name",
        "description": "description", "category": "category",
        "brand": "brand", "sku": "sku", "price": "price", "stock": "stock",
    }
    sql, params = ProductSQLBuilder(mapping, MySQLDialect()).build(
        ProductSearchRequest(query="Nike running shoes", limit=10)
    )
    assert "DROP" not in sql.upper()
    assert params["search_term_0"] == "%Nike%"
    assert params["search_term_1"] == "%running%"
    assert params["search_term_2"] == "%shoes%"
    assert sql.count(" AND ") >= 2
    assert "description" in sql
    assert "category" in sql
    assert "brand" in sql
    assert "sku" in sql


def test_sql_preserves_structured_filters():
    mapping = {
        "table": "products", "id": "id", "name": "name", "price": "price",
        "stock": "stock", "brand": "brand", "category": "category", "sku": "sku",
    }
    sql, params = ProductSQLBuilder(mapping, MySQLDialect()).build(
        ProductSearchRequest(
            brand="Nike", category="Shoes", min_price=1000,
            max_price=5000, in_stock_only=True,
        )
    )
    assert ":brand_value" in sql
    assert ":category_value" in sql
    assert ":min_price" in sql
    assert ":max_price" in sql
    assert ":stock_min" in sql
    assert params["brand_value"] == "Nike"
    assert params["category_value"] == "Shoes"


@pytest.mark.asyncio
async def test_planner_llm_failure_keeps_deterministic_result():
    class BrokenPlanner:
        async def plan(self, query):
            raise TimeoutError("provider timeout")

    result = await QueryPlanner(BrokenPlanner()).plan("Acme X200")
    assert result.intent == Intent.PRODUCT_SEARCH
    assert result.product_filters.product_name == "Acme X200"
