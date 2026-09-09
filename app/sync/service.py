"""Canonical merchant product synchronization."""
from __future__ import annotations
import logging
from datetime import datetime,timezone
from itertools import chain
from typing import Any,Iterable
from sqlalchemy.orm import Session
from app.db.models import Product
from app.sync.normalize import normalize_row,validate_mapping
from app.sync.result import SyncResult
from app.sync.upsert import upsert_products,zero_missing_stock
from app.sync.fingerprint import product_fingerprint
logger=logging.getLogger("app.sync")
class ProductSyncService:
 def __init__(self,db:Session,*,batch_size:int=100):self.db=db;self.batch_size=batch_size
 def sync_rows(self,store_id,raw_rows:Iterable[dict],mapping:dict,*,full_sync=False,source_datasource_id=None,hash_fallback=False):
  result=SyncResult(store_id=store_id);seen=set();batch=[]
  try:
   raw_iter=iter(raw_rows)
   try:first_raw=next(raw_iter)
   except StopIteration:
    result.mapping_validation={"ok":True,"mapping":{},"missing_required":[],"mapped_fields":[],"validated":False,"reason":"no rows to validate"};return result
   validation=validate_mapping(first_raw,mapping);result.mapping_validation=validation
   if not validation["ok"]:
    result.errors.append("schema mapping validation failed; missing required fields: "+", ".join(validation["missing_required"]));return result
   effective_mapping=dict(mapping or {});effective_mapping.update({f:c for f,c in validation["mapping"].items() if c and not effective_mapping.get(f)})
   for raw in chain((first_raw,),raw_iter):
    try:normalized=normalize_row(raw,effective_mapping)
    except Exception as exc:result.skipped+=1;result.record_quality(None);result.errors.append(f"normalize failed: {exc}");continue
    if normalized is None:result.skipped+=1;result.record_quality(None);continue
    pid=str(normalized["id"])
    if pid in seen:
     result.data_quality["source_rows"]+=1;result.record_duplicate(pid);result.skipped+=1;continue
    seen.add(pid);normalized["_source_fingerprint"]=product_fingerprint(normalized);normalized["attributes"]=dict(normalized.get("attributes") or {});normalized["attributes"]["_source_fingerprint"]=normalized["_source_fingerprint"]
    result.record_quality(normalized);batch.append(normalized)
    if len(batch)>=self.batch_size:upsert_products(self.db,store_id,batch,batch_size=self.batch_size,result=result,source_datasource_id=source_datasource_id,commit=False);batch=[]
   if batch:upsert_products(self.db,store_id,batch,batch_size=self.batch_size,result=result,source_datasource_id=source_datasource_id,commit=False)
   if full_sync:zero_missing_stock(self.db,store_id,seen,batch_size=self.batch_size,result=result,source_datasource_id=source_datasource_id,commit=False)
   self.db.flush()
  except Exception:self.db.rollback();logger.exception("product sync failed for store %s",store_id);raise
  result.data_quality["seen_ids"]=list(seen);result.data_quality["hash_fallback"]=bool(hash_fallback);return result
 def sync_from_connector(self,store_id,connector,table_name,mapping,*,full_sync=True,page_size=200,sync_state=None,sync_upper_bound=None,source_datasource_id=None,hash_fallback=False):
  columns=_mapping_columns(mapping);state=sync_state or {};updated_col=_mapping_column(mapping,"updated_at");created_col=_mapping_column(mapping,"created_at");id_col=_mapping_column(mapping,"id");timestamp_col=updated_col or created_col;watermark_at=_parse_datetime(state.get("watermark_at"));watermark_id=state.get("watermark_id");can_incremental=hasattr(connector,"fetch_product_rows_incremental") and bool(getattr(connector,"supports_incremental_sync",True));incremental=bool(state.get("initialized")) and bool(timestamp_col) and can_incremental;upper_bound=sync_upper_bound if timestamp_col and incremental else None
  def _iter_rows():
   if incremental:
    local_at,local_id=watermark_at,watermark_id
    while True:
     rows=connector.fetch_product_rows_incremental(table_name,columns,updated_column=updated_col,created_column=created_col,id_column=id_col,watermark_at=local_at,watermark_id=local_id,limit=page_size,upper_bound=upper_bound)
     if not rows:break
     yield from rows;last=rows[-1];next_at=last.get(timestamp_col) if timestamp_col else None;next_id=last.get(id_col) if id_col else None
     if timestamp_col and next_at is not None:local_at=next_at;local_id=str(next_id) if next_id is not None else None
     else:break
     if len(rows)<page_size:break
    return
   offset=0
   while True:
    try:rows=_fetch_page(connector,table_name,columns,limit=page_size,offset=offset)
    except Exception as exc:raise RuntimeError(f"connector fetch failed at offset={offset}: {exc}") from exc
    if not rows:break
    yield from rows
    if len(rows)<page_size:break
    offset+=page_size
  return self.sync_rows(store_id,_iter_rows(),mapping,full_sync=(full_sync and not incremental),source_datasource_id=source_datasource_id,hash_fallback=hash_fallback)
 def refresh_stock(self,store_id,stock_rows,mapping):
  result=SyncResult(store_id=store_id);raw_iter=iter(stock_rows)
  try:first_raw=next(raw_iter)
  except StopIteration:return result
  validation=validate_mapping(first_raw,mapping);result.mapping_validation=validation
  if not validation["ok"]:result.errors.append("schema mapping validation failed; missing required fields: "+", ".join(validation["missing_required"]));return result
  effective_mapping=dict(mapping or {});effective_mapping.update({f:c for f,c in validation["mapping"].items() if c and not effective_mapping.get(f)});batch=[]
  for raw in chain((first_raw,),raw_iter):
   normalized=normalize_row(raw,effective_mapping)
   if normalized is None:result.skipped+=1;continue
   result.record_quality(normalized);batch.append(normalized)
   if len(batch)>=self.batch_size:self._stock_only_upsert(store_id,batch,result);batch=[]
  if batch:self._stock_only_upsert(store_id,batch,result)
  return result
 def _stock_only_upsert(self,store_id,products,result):
  ids=[p["id"] for p in products];existing=self.db.query(Product).filter(Product.store_id==store_id,Product.id.in_(ids)).all();by_id={r.id:r for r in existing}
  for data in products:
   row=by_id.get(data["id"])
   if row is None:result.skipped+=1;continue
   if row.stock!=data.get("stock"):old=row.stock;row.stock=data.get("stock");result.updated+=1;result.record_stock_change(row.id,row.name,old,row.stock)
   else:result.unchanged+=1
  self.db.flush()
def _mapping_column(mapping,field):
 entry=mapping.get(field);return entry.get("column") if isinstance(entry,dict) else(entry or None)
def _mapping_columns(mapping):
 cols=[];seen=set()
 for field,entry in mapping.items():
  if field.startswith("_"):continue
  col=entry.get("column") if isinstance(entry,dict) else entry
  if col and col not in seen:seen.add(col);cols.append(col)
 return cols
def _parse_datetime(value:Any):
 if not value:return None
 if isinstance(value,datetime):return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
 try:p=datetime.fromisoformat(str(value).replace("Z","+00:00"));return p.astimezone(timezone.utc).replace(tzinfo=None) if p.tzinfo else p
 except(TypeError,ValueError):return None
def _fetch_page(connector,table_name,columns,*,limit,offset):
 if hasattr(connector,"fetch_product_rows"):return connector.fetch_product_rows(table_name,columns,limit=limit,offset=offset)
 raise TypeError(f"connector {type(connector).__name__} does not implement fetch_product_rows")
