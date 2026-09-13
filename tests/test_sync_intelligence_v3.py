from app.sync.fingerprint import product_fingerprint
from app.sync.result import SyncResult

def test_product_fingerprint_is_deterministic_and_order_independent():
    a={"id":"1","name":"Phone","price":100,"attributes":{"b":2,"a":1}}
    b={"attributes":{"a":1,"b":2},"price":100,"name":"Phone","id":"1"}
    assert product_fingerprint(a)==product_fingerprint(b)
    assert product_fingerprint(a)!=product_fingerprint({**a,"price":101})

def test_same_name_is_only_possible_duplicate():
    r=SyncResult(store_id="s")
    r.record_quality({"id":"1","name":"Phone","price":100,"category":"mobile"})
    r.record_quality({"id":"2","name":"Phone","price":200,"category":"accessories"})
    report=r.data_quality_report()
    assert report["duplicates"]["possible_duplicate_name_count"]==1
    assert report["duplicates"]["candidates"][0]["classification"]=="possible"
    assert report["duplicates"]["candidates"][0]["confidence_pct"]<90

def test_same_name_price_category_is_strong_candidate():
    r=SyncResult(store_id="s")
    r.record_quality({"id":"1","name":"Phone","price":100,"category":"mobile"})
    r.record_quality({"id":"2","name":"Phone","price":100,"category":"mobile"})
    candidate=r.data_quality_report()["duplicates"]["candidates"][0]
    assert candidate["classification"]=="strong_candidate"
    assert candidate["confidence_pct"]==95

def test_price_and_stock_changes_are_separate():
    r=SyncResult(store_id="s")
    r.record_price_change("1","Phone",100,90)
    r.record_stock_change("1","Phone",4,0)
    r.record_stock_change("2","Tablet",0,3)
    out=r.to_dict()
    assert out["price_changes"]["decreased"]==1
    assert out["stock_changes"]["became_out_of_stock"]==1
    assert out["stock_changes"]["came_back_in_stock"]==1
