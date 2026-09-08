from app.connectors.field_classifier import classify_field
from app.connectors.field_mapper import build_candidate_mapping, resolve_mapping
from app.connectors.mapping_engine import MappingEngine


def test_all_mapping_paths_share_brand_and_category():
    columns = ["product_name", "brand_name", "category_name", "sale_price", "qty"]

    candidates = build_candidate_mapping([
        {"name": name, "type": "varchar", "samples": ["Nike", "Adidas"]}
        for name in columns
    ])
    assert "brand" in candidates
    assert "category" in candidates
    assert candidates["brand"][0]["column"] == "brand_name"
    assert candidates["category"][0]["column"] == "category_name"

    classified = {classify_field(name) for name in columns}
    assert "brand" in classified
    assert "category" in classified

    legacy = {candidate.field for candidate in MappingEngine().suggest(columns)}
    assert "brand" in legacy
    assert "category" in legacy


def test_resolver_does_not_assign_one_column_to_multiple_fields():
    candidates = {
        "price": [{"column": "amount", "score": 0.90}],
        "compare_at_price": [{"column": "amount", "score": 0.89}],
    }
    resolved = resolve_mapping(candidates)
    assert len(resolved["resolved"]) == 1


def test_mapping_detects_common_extended_fields():
    columns = [
        {"name": "SKU", "type": "varchar", "samples": ["ABC-1", "ABC-2"]},
        {"name": "image_url", "type": "varchar", "samples": ["https://example.com/a.jpg"]},
        {"name": "color", "type": "varchar", "samples": ["black", "white"]},
        {"name": "rating", "type": "numeric", "samples": [4.5, 4.0]},
        {"name": "review_count", "type": "integer", "samples": [12, 4]},
    ]
    candidates = build_candidate_mapping(columns)
    assert candidates["sku"][0]["column"] == "SKU"
    assert candidates["image"][0]["column"] == "image_url"
    assert candidates["color"][0]["column"] == "color"
    assert candidates["rating"][0]["column"] == "rating"
    assert candidates["review_count"][0]["column"] == "review_count"
