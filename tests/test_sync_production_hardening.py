from app.sync.fingerprint import product_fingerprint
from app.sync.normalize import discover_mapping, normalize_row
from app.sync.result import SyncResult


def test_fingerprint_changes_when_sku_changes():
    base={"id":"1","sku":"SKU-1","name":"Phone","price":100,"attributes":{}}
    assert product_fingerprint(base)!=product_fingerprint({**base,"sku":"SKU-2"})


def test_sku_is_discovered_without_treating_it_as_product_id():
    raw={"product_code":"P-1","title":"Phone","sku":"SKU-9","price":"100"}
    mapping=discover_mapping(raw,{})
    assert mapping["id"]=="product_code"
    assert mapping["sku"]=="sku"
    normalized=normalize_row(raw,{})
    assert normalized["id"]=="P-1"
    assert normalized["attributes"]["sku"]=="SKU-9"


def test_reconciliation_uses_accepted_products_not_raw_rows():
    r=SyncResult(store_id="s")
    r.record_quality({"id":"1","name":"Phone"})
    r.record_duplicate("1")
    r.set_reconciliation(source_rows=2,accepted_products=1,db_count=1,rejected=0,duplicates=1,known_stale=0)
    assert r.reconciliation["source_rows"]==2
    assert r.reconciliation["accepted_products"]==1
    assert r.reconciliation["unexplained"]==0
    assert r.reconciliation["reconciled"] is True


def test_large_change_counters_are_not_limited_by_sample_storage():
    r=SyncResult(store_id="s")
    for i in range(1205):
        r.record_price_change(str(i),"Phone",100,101)
        r.record_stock_change(str(i),"Phone",1,0)
    report=r.to_dict()
    assert report["price_changes"]["total"]==1205
    assert report["price_changes"]["increased"]==1205
    assert report["stock_changes"]["total"]==1205
    assert report["stock_changes"]["became_out_of_stock"]==1205
    assert len(report["price_changes"]["items"])==100


def test_same_name_alone_is_not_hard_duplicate():
    r=SyncResult(store_id="s")
    r.record_quality({"id":"1","name":"Phone","price":100,"category":"mobile"})
    r.record_quality({"id":"2","name":"Phone","price":200,"category":"accessories"})
    candidate=r.data_quality_report()["duplicates"]["candidates"][0]
    assert candidate["classification"]=="possible"
    assert candidate["confidence_pct"]<90
