"""Batch upsert of normalized products into the local products table."""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.models import Product
from app.sync.result import SyncResult
_TRACKED_FIELDS=("name","description","category","price","currency","stock","image_url","product_url","source_datasource_id","attributes")

def _changed(existing,data):
    incoming_fp=data.get("_source_fingerprint")
    if incoming_fp and existing.source_fingerprint:
        return incoming_fp != existing.source_fingerprint
    for field in _TRACKED_FIELDS:
        incoming=data.get(field)
        if field=="attributes":
            if (getattr(existing,field,{}) or {})!=(incoming or {}):return True
        elif getattr(existing,field,None)!=incoming:return True
    return False

def _persist_attributes(db,store_id,product_id,attributes):
    db.execute(text("UPDATE products SET attributes=:attributes WHERE product_id=:product_id AND store_id=:store_id"),{"attributes":attributes or {},"product_id":product_id,"store_id":store_id})

def upsert_products(db:Session,store_id,products,*,batch_size=100,result=None,source_datasource_id=None,commit=True):
    if result is None:result=SyncResult(store_id=store_id)
    if not products:return result
    ids=[p["id"] for p in products]
    existing_rows=db.query(Product).filter(Product.store_id==store_id,Product.id.in_(ids)).all()
    by_id={r.id:r for r in existing_rows};pending=0
    for data in products:
        pid=data["id"];existing=by_id.get(pid);data=dict(data)
        if source_datasource_id:data["source_datasource_id"]=source_datasource_id
        data["attributes"]=data.get("attributes") or {}
        incoming_fp=data.get("_source_fingerprint")
        if existing is None:
            row=Product(id=pid,store_id=store_id,name=data["name"],description=data.get("description"),category=data.get("category"),price=data.get("price"),currency=data.get("currency"),stock=data.get("stock"),image_url=data.get("image_url"),product_url=data.get("product_url"),source_datasource_id=data.get("source_datasource_id"),source_fingerprint=incoming_fp)
            db.add(row);db.flush();_persist_attributes(db,store_id,pid,data["attributes"]);row.attributes=data["attributes"];by_id[pid]=row;result.created+=1;pending+=1
        elif _changed(existing,data):
            old_price=existing.price;old_stock=existing.stock;old_name=existing.name
            for field in _TRACKED_FIELDS:
                if field!="attributes" and field in data:setattr(existing,field,data.get(field))
            if incoming_fp:existing.source_fingerprint=incoming_fp
            _persist_attributes(db,store_id,pid,data["attributes"]);existing.attributes=data["attributes"];result.updated+=1;pending+=1
            try:
                new_price=data.get("price")
                if old_price is not None and new_price is not None and old_price!=new_price:result.record_price_change(pid,old_name,old_price,new_price)
            except Exception:pass
            try:
                new_stock=data.get("stock")
                if old_stock!=new_stock and (old_stock is not None or new_stock is not None):result.record_stock_change(pid,old_name,old_stock,new_stock)
            except Exception:pass
        else:result.unchanged+=1
        if commit and pending>=batch_size:db.commit();pending=0
    if commit and pending:db.commit()
    return result

def zero_missing_stock(db,store_id,seen_ids,*,batch_size=200,result=None,source_datasource_id=None,commit=True):
    if result is None:result=SyncResult(store_id=store_id)
    q=db.query(Product).filter(Product.store_id==store_id)
    q=q.filter(Product.source_datasource_id==source_datasource_id) if source_datasource_id else q.filter(Product.source_datasource_id.is_(None))
    if seen_ids:q=q.filter(~Product.id.in_(seen_ids))
    pending=0
    for row in q:
        if row.stock is None or float(row.stock)!=0.0:
            old=row.stock;row.stock=0.0;result.stock_zeroed+=1;result.record_stock_change(row.id,row.name,old,0);pending+=1
        if commit and pending>=batch_size:db.commit();pending=0
    if commit and pending:db.commit()
    return result
