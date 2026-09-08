"""DataSource CRUD + discover/test helpers."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session
from app.connectors.credential_store import get_credential_store
from app.connectors.factory import ConnectorFactory
from app.connectors.mapping_engine import MappingEngine
from app.core.network_guard import assert_safe_connection_host
from app.db.models import DataSource, Store
from app.discovery.scanners.sql_scanner import SQLSchemaScanner
from app.discovery.table_detector import detect_table
from app.products.sql_identifier import validate_identifier
logger=logging.getLogger("app.datasources")
SUPPORTED_SYNC_TYPES={"postgresql","mysql","postgres","rest"}; AUTO_MAP_THRESHOLD=.85
class DataSourceService:
 def __init__(self,db): self.db=db
 def get(self,store_id,datasource_id): return self.db.query(DataSource).filter(DataSource.store_id==store_id,DataSource.id==datasource_id).first()
 def list_for_store(self,store_id): return self.db.query(DataSource).filter(DataSource.store_id==store_id).order_by(DataSource.created_at.desc()).all()
 def list_active(self): return self.db.query(DataSource).filter(DataSource.active.is_(True)).all()
 def create(self,store_id,*,name,connector_type,connection_url=None,api_base_url=None,table_name=None,mapping=None,active=True,full_sync=True,validate_connection=True):
  if self.db.query(Store).filter(Store.id==store_id).first() is None: raise ValueError("store not found")
  ctype=connector_type.lower().strip(); ctype="postgresql" if ctype=="postgres" else ctype
  if ctype not in {"postgresql","mysql","rest"}: raise ValueError(f"unsupported connector_type: {connector_type}")
  if ctype!="rest" and not connection_url: raise ValueError("connection_url required for SQL connectors")
  if ctype=="rest" and not api_base_url: raise ValueError("api_base_url required for REST connectors")
  if validate_connection and not self._test_connection_sync(ctype,connection_url,api_base_url=api_base_url): raise ConnectionError("connection test failed")
  if table_name: validate_identifier(table_name)
  ds=DataSource(id=str(uuid.uuid4()),store_id=store_id,name=name or "default",connector_type=ctype,connection_url=get_credential_store().encrypt(connection_url) if connection_url else None,api_base_url=api_base_url,table_name=table_name,mapping=mapping,active=active,full_sync=full_sync,created_at=datetime.utcnow(),updated_at=datetime.utcnow())
  self.db.add(ds); self.db.commit(); self.db.refresh(ds); return ds
 def update(self,store_id,datasource_id,**fields:Any):
  ds=self.get(store_id,datasource_id)
  if ds is None: raise LookupError("datasource not found")
  allowed={"name","connection_url","api_base_url","table_name","mapping","active","full_sync","credential_ref"}; fields={k:v for k,v in fields.items() if k in allowed}
  fields.pop("connection_url",None) if fields.get("connection_url") is None else None
  if fields.get("table_name"): validate_identifier(fields["table_name"])
  new_url=fields.get("connection_url"); new_api=fields.get("api_base_url")
  if ds.connector_type=="rest" and new_url: raise ValueError("connection_url is not valid for REST connectors")
  if ds.connector_type!="rest" and "api_base_url" in fields and new_api is not None: raise ValueError("api_base_url is only valid for REST connectors")
  if new_url:
   if not self._test_connection_sync(ds.connector_type,new_url): raise ConnectionError("connection test failed")
   fields["connection_url"]=get_credential_store().encrypt(new_url)
  if new_api:
   if ds.connector_type!="rest": raise ValueError("api_base_url is only valid for REST connectors")
   if not self._test_connection_sync("rest",None,api_base_url=new_api): raise ConnectionError("REST connection test failed")
  for key,value in fields.items():
   if key=="name" and value is None: continue
   setattr(ds,key,value)
  ds.updated_at=datetime.utcnow(); self.db.commit(); self.db.refresh(ds); return ds
 def delete(self,store_id,datasource_id):
  ds=self.get(store_id,datasource_id)
  if ds is None:return False
  self.db.delete(ds); self.db.commit(); return True
 def record_sync_result(self,store_id,datasource_id,*,status,error=None):
  ds=self.get(store_id,datasource_id)
  if ds is None:return
  ds.last_sync_at=datetime.utcnow(); ds.last_sync_status=status; ds.last_sync_error=error; ds.updated_at=datetime.utcnow(); self.db.commit()
 last_test_error=None
 def test_connection(self,connector_type,connection_url=None,api_base_url=None):
  ctype=connector_type.lower().strip(); ctype="postgresql" if ctype=="postgres" else ctype; self.last_test_error=None; return self._test_connection_sync(ctype,connection_url,api_base_url=api_base_url)
 def _test_connection_sync(self,connector_type,connection_url,api_base_url=None):
  import asyncio
  try:
   if connector_type in {"postgresql","mysql"}:
    if not connection_url:return False
    assert_safe_connection_host(connection_url); connector=ConnectorFactory.create(connector_type,connection_url)
   elif connector_type=="rest":
    if not api_base_url:return False
    assert_safe_connection_host(api_base_url)
    from app.connectors.config import ConnectorConfig
    connector=ConnectorFactory.create(ConnectorConfig(connector_type="rest",api_base_url=api_base_url))
   else:return False
   coro=connector.test_connection()
   if asyncio.iscoroutine(coro):
    try: asyncio.get_running_loop(); running=True
    except RuntimeError: running=False
    if running:
     import concurrent.futures
     with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:result=pool.submit(asyncio.run,coro).result(timeout=20)
    else:result=asyncio.run(coro)
    if not result and getattr(connector,"last_test_error",None) and not self.last_test_error:self.last_test_error=connector.last_test_error
    return bool(result)
   return bool(coro)
  except Exception as exc: logger.exception("connection test failed"); self.last_test_error=f"{type(exc).__name__}: {exc}"; return False
 def validate_mapping(self,connection_url,table_name,mapping):
  if not mapping:raise ValueError("mapping cannot be empty")
  validate_identifier(table_name); schema=SQLSchemaScanner(connection_url).scan(); table=next((t for t in schema.tables if t.name==table_name),None)
  if table is None:raise ValueError(f"mapped table not found: {table_name}")
  available={c.name for c in table.columns}; used={}
  for field,entry in mapping.items():
   if field=="_sync_state":continue
   col=entry.get("column") if isinstance(entry,dict) else entry
   if not col:continue
   validate_identifier(str(col))
   if col not in available:raise ValueError(f"mapping column not found in table: {col}")
   if col in used and used[col]!=field:raise ValueError(f"column {col!r} is mapped to both {used[col]!r} and {field!r}")
   used[col]=field
  for required in ("id","name"):
   entry=mapping.get(required); col=entry.get("column") if isinstance(entry,dict) else entry
   if not col:raise ValueError(f"mapping must include semantic field '{required}'")
 def discover(self,connection_url,*,auto_threshold=AUTO_MAP_THRESHOLD):
  assert_safe_connection_host(connection_url); schema=SQLSchemaScanner(connection_url).scan(); engine=MappingEngine(); out=[]
  for table in schema.tables:
   names=[c.name for c in table.columns]; dicts=[{"name":c.name,"type":c.data_type} for c in table.columns]; score=detect_table(table.name,dicts); suggestions=engine.suggest(names); resolved={}; confirm={}
   for candidate in suggestions:
    target=resolved if candidate.confidence>=auto_threshold and candidate.column not in resolved.values() else confirm
    if target is resolved:resolved[candidate.field]=candidate.column
    else:confirm.setdefault(candidate.field,[]).append({"column":candidate.column,"confidence":candidate.confidence})
   out.append({"table":table.name,"score":score,"columns":names,"proposed_mapping":resolved,"needs_confirmation":confirm})
  out.sort(key=lambda t:t["score"],reverse=True); best=out[0] if out else None
  return {"tables":out,"recommended_table":best["table"] if best else None,"recommended_mapping":best["proposed_mapping"] if best else {},"needs_confirmation":best["needs_confirmation"] if best else {}}
 @staticmethod
 def decrypt_connection_url(ds):return get_credential_store().decrypt(ds.connection_url)
 def build_sync_job(self,ds):
  # Queue only immutable identifiers/config. Never put credentials in Redis.
  return {"store_id":ds.store_id,"datasource_id":ds.id,"job_type":"product_sync","full_sync":bool(ds.full_sync)}
