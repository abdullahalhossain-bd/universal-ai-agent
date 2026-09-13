from app.connectors.field_mapper import build_candidate_mapping, resolve_mapping
from app.connectors.field_scoring import score_column
from app.connectors.mapping_engine import MappingEngine


def test_exact_canonical_names_auto_map_without_samples():
    columns = [
        {"name": "id"},
        {"name": "name"},
        {"name": "price"},
        {"name": "brand"},
        {"name": "category"},
    ]

    result = resolve_mapping(build_candidate_mapping(columns))
    resolved = result["resolved"]

    assert resolved["id"]["column"] == "id"
    assert resolved["name"]["column"] == "name"
    assert resolved["price"]["column"] == "price"
    assert resolved["brand"]["column"] == "brand"
    assert resolved["category"]["column"] == "category"


def test_common_aliases_auto_map_with_sparse_metadata():
    columns = [
        {"name": "product_name"},
        {"name": "selling_price"},
        {"name": "brand_name"},
        {"name": "category_name"},
        {"name": "image_url"},
    ]

    result = resolve_mapping(build_candidate_mapping(columns))
    resolved = result["resolved"]

    assert resolved["name"]["column"] == "product_name"
    assert resolved["price"]["column"] == "selling_price"
    assert resolved["brand"]["column"] == "brand_name"
    assert resolved["category"]["column"] == "category_name"
    assert resolved["image"]["column"] == "image_url"


def test_mapping_engine_uses_same_resolver_and_prevents_duplicate_columns():
    suggestions = MappingEngine().suggest(["id", "name", "brand", "category"])
    pairs = {(item.field, item.column) for item in suggestions}

    assert ("id", "id") in pairs
    assert ("name", "name") in pairs
    assert ("brand", "brand") in pairs
    assert ("category", "category") in pairs
    assert len({item.column for item in suggestions}) == len(suggestions)


def test_global_assignment_beats_greedy_field_order():
    # A greedy resolver would give ``shared`` to price (0.95) and leave sku
    # unmatched. The global optimum is price->fallback and sku->shared.
    candidates = {
        "price": [
            {"column": "shared", "score": 0.95},
            {"column": "fallback", "score": 0.90},
        ],
        "sku": [
            {"column": "shared", "score": 0.94},
        ],
    }

    result = resolve_mapping(candidates)
    resolved = result["resolved"]

    assert resolved["price"]["column"] == "fallback"
    assert resolved["sku"]["column"] == "shared"
    assert len({item["column"] for item in resolved.values()}) == len(resolved)


def test_overlapping_alias_has_one_owner_and_primary_field_wins_tie():
    candidates = {
        "price": [
            {"column": "regular_price", "score": 0.90},
        ],
        "compare_at_price": [
            {"column": "regular_price", "score": 0.90},
        ],
    }

    result = resolve_mapping(candidates)
    resolved = result["resolved"]

    assert resolved["price"]["column"] == "regular_price"
    assert "compare_at_price" not in resolved
    assert len({item["column"] for item in resolved.values()}) == len(resolved)


def test_score_is_high_enough_for_obvious_exact_fields():
    assert score_column("name", "name") >= 0.90
    assert score_column("brand", "brand") >= 0.90
    assert score_column("category", "category") >= 0.90


def test_ambiguous_alias_does_not_silently_map_below_threshold():
    candidates = {
        "price": [
            {"column": "regular_price", "score": 0.70},
        ],
        "compare_at_price": [
            {"column": "regular_price", "score": 0.70},
        ],
    }

    result = resolve_mapping(candidates)

    assert result["resolved"] == {}
    assert "price" in result["needs_confirmation"]
    assert "compare_at_price" in result["needs_confirmation"]
