from app.sync.result import SyncResult

def test_duplicate_name_is_only_possible_and_stronger_with_price_category():
    r=SyncResult(store_id="s")
    r.record_quality({"id":"1","name":"iPhone 15","price":89999,"category":"phone"})
    r.record_quality({"id":"2","name":" iphone   15 ","price":89999,"category":"phone"})
    assert len(r.duplicate_names)==1
    assert r.duplicate_candidates[0]["confidence_pct"]==95

def test_price_and_stock_change_direction():
    r=SyncResult(store_id="s")
    r.record_price_change("1","Phone",89999,84999)
    r.record_price_change("2","Laptop",50000,55000)
    r.record_stock_change("1","Phone",4,0)
    r.record_stock_change("2","Laptop",0,3)
    report=r.to_dict()
    assert report["price_changes"]["decreased"]==1
    assert report["price_changes"]["increased"]==1
    assert report["stock_changes"]["became_out_of_stock"]==1
    assert report["stock_changes"]["came_back_in_stock"]==1

def test_health_score_penalizes_invalid_and_duplicate_data():
    r=SyncResult(store_id="s")
    for i in range(10):
        r.record_quality({"id":str(i),"name":"same","price":-1,"image_url":"bad","product_url":"bad"})
    assert r.calculate_health_score()<100
