from app.sync.result import SyncResult


def test_sync_result_data_quality_report_counts_present_and_missing_fields():
    result = SyncResult(store_id="store-1")
    result.record_quality({
        "id": "1",
        "name": "Laptop",
        "price": 1000,
        "image_url": "https://example.com/1.jpg",
        "product_url": "https://example.com/1",
    })
    result.record_quality({
        "id": "2",
        "name": "Mouse",
        "price": None,
        "image_url": None,
        "product_url": "https://example.com/2",
    })

    report = result.data_quality_report()

    assert report["products"] == 2
    assert report["source_rows"] == 2
    assert report["skipped_rows"] == 0
    assert report["fields"]["name"] == {"present": 2, "missing": 0, "coverage_pct": 100.0}
    assert report["fields"]["price"] == {"present": 1, "missing": 1, "coverage_pct": 50.0}
    assert report["fields"]["image_url"] == {"present": 1, "missing": 1, "coverage_pct": 50.0}
    assert report["fields"]["product_url"] == {"present": 2, "missing": 0, "coverage_pct": 100.0}


def test_sync_result_data_quality_tracks_skipped_source_rows():
    result = SyncResult(store_id="store-1")
    result.record_quality({
        "id": "1",
        "name": "Laptop",
        "price": 1000,
        "image_url": None,
        "product_url": None,
    })
    result.record_quality(None)

    report = result.data_quality_report()

    assert report["products"] == 1
    assert report["source_rows"] == 2
    assert report["skipped_rows"] == 1
    assert report["fields"]["image_url"]["missing"] == 1
    assert report["fields"]["product_url"]["missing"] == 1


def test_sync_result_to_dict_exposes_data_quality():
    result = SyncResult(store_id="store-1")
    result.record_quality({"id": "1", "name": "Phone"})

    payload = result.to_dict()

    assert "data_quality" in payload
    assert payload["data_quality"]["products"] == 1
    assert payload["data_quality"]["fields"]["price"]["missing"] == 1
