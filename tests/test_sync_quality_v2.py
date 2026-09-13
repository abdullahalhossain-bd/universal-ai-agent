from app.sync.mapping_confidence import discover_mapping_with_confidence
from app.sync.result import SyncResult


def test_confidence_mapping_prefers_semantic_columns():
    result = discover_mapping_with_confidence({"product_title": "Phone", "selling_price": 100, "thumbnail": "https://x.test/a.jpg", "permalink": "https://x.test/p"})
    assert result["name"]["column"] == "product_title"
    assert result["price"]["column"] == "selling_price"
    assert result["image_url"]["column"] == "thumbnail"
    assert result["product_url"]["column"] == "permalink"
    assert result["name"]["confidence_pct"] >= 80


def test_result_detects_invalid_and_duplicates():
    result = SyncResult(store_id="s")
    row = {"id":"1","name":"iPhone 15","price":-1,"stock":-2,"currency":"XYZ","image_url":"not-a-url","product_url":"bad"}
    result.record_quality(row)
    result.record_quality({**row, "id":"2"})
    report = result.data_quality_report()
    assert report["duplicates"]["possible_duplicate_name_count"] == 1
    assert "negative_price" in report["invalid_data"]
    assert "invalid_stock" in report["invalid_data"]
    assert "invalid_currency" in report["invalid_data"]
    assert "malformed_url" in report["invalid_data"]
    assert "invalid_image_url" in report["invalid_data"]
