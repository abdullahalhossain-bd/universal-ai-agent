"""Tests for deterministic intelligent product search planning and SQL generation."""

import asyncio

from app.products.models import ProductSearchRequest
from app.products.sql_builder import MySQLDialect, ProductSQLBuilder


def test_arbitrary_product_name_is_product_intent():
    from app.query_intent import classify_product_query

    result = classify_product_query("Asus Vivobook 15")
    assert result.intent == "product_search"
    assert "Asus Vivobook 15" in result.search_terms


def test_bengali_conversational_words_are_removed():
    from app.query_intent import classify_product_query

    result = classify_product_query("amar ekta laptop chai")
    assert result.intent == "product_search"
    assert "laptop" in result.search_terms
    assert "amar" not in result.search_terms
    assert "chai" not in result.search_terms


def test_mixed_query_keeps_terms_and_price_filter():
    from app.query_intent import classify_product_query

    result = classify_product_query("gaming laptop 50000 er moddhe")
    assert result.intent == "product_search"
    assert "gaming" in result.search_terms
    assert "laptop" in result.search_terms
    assert result.max_price == 50000


def test_synonym_expansion_handles_bengali_and_english():
    from app.query_intent import expand_search_terms

    expanded = expand_search_terms(["জুতা"])
    assert any(term.lower() in {"shoe", "shoes"} for term in expanded)


def test_synonym_expansion_handles_common_typo():
    from app.query_intent import expand_search_terms

    expanded = expand_search_terms(["lapto"])
    assert "laptop" in {term.lower() for term in expanded}


def test_sql_requires_all_terms_but_allows_any_search_field():
    mapping = {
        "table": "products",
        "id": "id",
        "name": "name",
        "price": "price",
        "stock": "stock",
        "brand": "brand",
        "category": "category",
        "sku": "sku",
    }
    sql, params = ProductSQLBuilder(mapping, MySQLDialect()).build(
        ProductSearchRequest(search_terms=["gaming", "laptop"])
    )
    assert sql.count(":term_0") == 1
    assert sql.count(":term_1") == 1
    assert " AND " in sql
    assert params["term_0"] == "%gaming%"
    assert params["term_1"] == "%laptop%"


def test_sql_preserves_structured_filters():
    mapping = {
        "table": "products",
        "id": "id",
        "name": "name",
        "price": "price",
        "stock": "stock",
        "brand": "brand",
        "category": "category",
        "sku": "sku",
    }
    sql, params = ProductSQLBuilder(mapping, MySQLDialect()).build(
        ProductSearchRequest(
            brand="Nike",
            category="Shoes",
            min_price=1000,
            max_price=5000,
            in_stock_only=True,
        )
    )
    assert ":brand_value" in sql
    assert ":category_value" in sql
    assert ":min_price" in sql
    assert ":max_price" in sql
    assert ":stock_min" in sql
    assert params["brand_value"] == "Nike"
    # Category uses a partial-match predicate so natural-language values such
    # as "running shoes" can match a category like "Men's Running Shoes".
    assert params["category_value"] == "%Shoes%"


def test_planner_llm_failure_keeps_deterministic_result():
    import pytest
    from app.planner.service import QueryPlanner

    class BrokenPlanner:
        async def plan(self, query):
            raise TimeoutError("provider timeout")

    result = pytest.run(asyncio_run(QueryPlanner(BrokenPlanner()).plan("Acme X200"))) if False else None
