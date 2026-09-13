from app.sync.result import SyncResult


def test_sync_result_persists_every_issue_while_samples_remain_capped():
    persisted = []
    result = SyncResult(store_id="store-1", issue_sink=lambda field, item: persisted.append((field, item)))
    for i in range(1100):
        result._issue("product_url", {"id": str(i), "reason": "missing"}, issue_type="missing_field")
    assert len(persisted) == 1100
    assert len(result.data_quality["issue_samples"]["product_url"]) == 1000


def test_price_and_stock_changes_are_persisted_to_issue_sink():
    persisted = []
    result = SyncResult(store_id="store-1", issue_sink=lambda field, item: persisted.append((field, item)))
    result.record_price_change("p1", "Phone", 100, 110)
    result.record_stock_change("p1", "Phone", 2, 0)
    assert {field for field, _ in persisted} == {"price_changes", "stock_changes"}
    assert persisted[0][1]["issue_type"] == "price_change"
    assert persisted[1][1]["issue_type"] == "stock_change"


def test_health_score_penalizes_unexplained_reconciliation_gap():
    result = SyncResult(store_id="store-1")
    result.data_quality["products"] = 100
    result.data_quality["source_rows"] = 100
    for field in ("name", "price", "image_url", "product_url"):
        result.data_quality["fields"][field]["present"] = 100
    result.set_reconciliation(source_rows=100, accepted_products=100, db_count=110, known_stale=0)
    assert result.calculate_health_score() < 100
