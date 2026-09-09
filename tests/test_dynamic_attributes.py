from app.planner.rule_planner import plan
from app.products.semantic_attributes import deterministic_extract
from app.sync.normalize import normalize_row


def test_normalize_keeps_attributes_structured_without_description_pollution():
    mapping = {
        "id": "id",
        "name": "name",
        "description": "description",
        "attributes": {
            "ram": {"column": "ram_gb", "aliases": ["memory", "র‍্যাম"]},
            "finish": {"column": "finish_name", "aliases": ["color", "colour", "রং"]},
            "size": {"column": "shirt_size", "aliases": ["মাপ"]},
        },
    }
    row = normalize_row(
        {"id": "1", "name": "Laptop", "description": "Office laptop", "ram_gb": "16GB", "finish_name": "black", "shirt_size": "XL"},
        mapping,
    )
    assert row["attributes"] == {"ram": "16GB", "finish": "black", "size": "XL"}
    assert row["description"] == "Office laptop"


def test_semantic_attribute_extraction_uses_only_declared_schema():
    schema = {
        "ram": ["ram", "memory", "র‍্যাম"],
        "finish": ["finish", "color", "colour", "রং"],
        "size": ["size", "মাপ"],
    }
    assert deterministic_extract("16GB RAM black color XL size", schema) == {
        "ram": "16gb",
        "finish": "black",
        "size": "xl",
    }


def test_planner_extracts_multiple_merchant_attributes_and_keeps_product_term():
    class StoreTerms(set):
        attribute_schema = {
            "ram": ["ram", "memory"],
            "finish": ["finish", "color", "colour"],
            "size": ["size"],
        }

    terms = StoreTerms({"laptop", "ram", "memory", "finish", "color", "size", "16gb", "black", "xl"})
    planned = plan("16GB memory black color XL size laptop", store_terms=terms)
    assert planned.product_filters.attributes == {"ram": "16gb", "finish": "black", "size": "xl"}
    assert planned.product_filters.product_name == "laptop"


def test_planner_handles_attribute_only_queries():
    class StoreTerms(set):
        attribute_schema = {"ram": ["ram", "memory"]}

    terms = StoreTerms({"ram", "memory", "16gb"})
    planned = plan("8GB memory", store_terms=terms)
    assert planned.product_filters.attributes == {"ram": "8gb"}
    assert planned.product_filters.product_name is None


def test_existence_words_do_not_become_stock_filter_without_availability_question():
    assert plan("laptop ta kemon ase", store_terms={"laptop"}).product_filters.in_stock is False
    assert plan("laptop ase", store_terms={"laptop"}).product_filters.in_stock is True
    assert plan("tomar kase ki laptop ase", store_terms={"laptop"}).product_filters.in_stock is True
