"""Merchant datasource onboarding and sync observability API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.tenant import get_current_store
from app.core.features import FEATURE_DATABASE_SYNC,require_feature
from app.core.config import settings
from app.datasources.redaction import public_datasource_dict,redact_url
from app.datasources.service import DataSourceService,SUPPORTED_SYNC_TYPES
from app.db.database import get_db
from app.db.models import Product,Store,SyncRun
from app.sync.media_models import ProductMediaHealth
from app.sync.queue import SyncQueue
from app.sync.quality import valid_http_url
from app.sync.url_health import verify_product_urls
router=APIRouter(prefix="/v1/datasources",tags=["datasources"])
class CreateDataSourceRequest(BaseModel):
 name:str="default";connector_type:str;connection_url:str|None=None;api_base_url:str|None=None;table_name:str|None=None;mapping:dict[str,Any]|None=None;active:bool=True;full_sync:bool=True;skip_connection_test:bool=False
class UpdateDataSourceRequest(BaseModel):
 name:str|None=None;connection_url:str|None=None;api_base_url:str|None=None;table_name:str|None=None;mapping:dict[str,Any]|None=None;active:bool|None=None;full_sync:bool|None=None
class TestConnectionRequest(BaseModel):connector_type:str;connection_url:str|None=None;api_base_url:str|None=None
class DiscoverRequest(BaseModel):connection_url:str=Field(min_length=1);connector_type:str="postgresql"
class SchemaApprovalRequest(BaseModel):action:str=Field(pattern="^(approve|reject)$")
@router.post("")
async def create_datasource(payload:CreateDataSourceRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 try:ds=DataSourceService(db).create(store.id,name=payload.name,connector_type=payload.connector_type,connection_url=payload.connection_url,api_base_url=payload.api_base_url,table_name=payload.table_name,mapping=payload.mapping,active=payload.active,full_sync=payload.full_sync,validate_connection=not payload.skip_connection_test)
 except(ValueError,ConnectionError) as exc:raise HTTPException(400,detail=str(exc)) from exc
 return public_datasource_dict(ds)
@router.get("")
def list_datasources(db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);items=DataSourceService(db).list_for_store(store.id);return {"count":len(items),"items":[public_datasource_dict(ds) for ds in items]}
@router.post("/debug/egress-ip")
async def debug_egress_ip(store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);import httpx
 try:
  async with httpx.AsyncClient(timeout=8) as client:r=await client.get("https://api.ipify.org?format=json");r.raise_for_status();return {"egress_ip":r.json().get("ip")}
 except Exception as exc:raise HTTPException(502,detail=f"could not determine egress ip: {type(exc).__name__}") from exc
@router.post("/test")
async def test_connection(payload:TestConnectionRequest,store:Store=Depends(get_current_store),db:Session=Depends(get_db)):
 require_feature(store,FEATURE_DATABASE_SYNC);service=DataSourceService(db);connected=service.test_connection(payload.connector_type,connection_url=payload.connection_url,api_base_url=payload.api_base_url);return {"connected":connected,"connector_type":payload.connector_type.lower(),"connection_url":redact_url(payload.connection_url),"error":None if connected else service.last_test_error}
@router.post("/discover")
def discover_schema(payload:DiscoverRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);ctype="postgresql" if payload.connector_type.lower()=="postgres" else payload.connector_type.lower()
 if ctype not in {"postgresql","mysql"}:raise HTTPException(400,detail="discovery supported only for postgresql/mysql")
 service=DataSourceService(db)
 if not service.test_connection(ctype,payload.connection_url):raise HTTPException(400,detail="connection test failed")
 try:result=service.discover(payload.connection_url)
 except Exception as exc:raise HTTPException(400,detail=f"discovery failed: {type(exc).__name__}") from exc
 result["connection_url"]=redact_url(payload.connection_url);return result
@router.get("/{datasource_id}")
def get_datasource(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);ds=DataSourceService(db).get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 return public_datasource_dict(ds)
@router.get("/{datasource_id}/quality")
async def get_sync_quality(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);ds=DataSourceService(db).get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 products=db.query(Product).filter(Product.store_id==store.id,Product.source_datasource_id==datasource_id,Product.is_active.is_(True)).all();total=len(products);fields={}
 for f in ("name","price","image_url","product_url"):
  present=sum(1 for p in products if getattr(p,f,None) not in(None,""));fields[f]={"present":present,"missing":total-present,"coverage_percent":round(present/total*100,2) if total else 0.0}
 latest=db.query(SyncRun).filter(SyncRun.store_id==store.id,SyncRun.datasource_id==datasource_id).order_by(SyncRun.started_at.desc()).first();report=(latest.quality_report if latest else {}) or {};dq=report.get("data_quality") or {};duplicates=dq.get("duplicates") or {};invalid=dq.get("invalid_data") or {};media_rows=db.query(ProductMediaHealth).filter(ProductMediaHealth.store_id==store.id,ProductMediaHealth.source_datasource_id==datasource_id).all();media={"products_checked":len(media_rows),"url":{"missing":sum(r.url_status=="missing" for r in media_rows),"valid":sum(r.url_status=="valid" for r in media_rows),"broken":sum(r.url_status=="broken" for r in media_rows)},"image":{"missing":sum(r.image_status=="missing" for r in media_rows),"valid":sum(r.image_status=="valid" for r in media_rows),"broken":sum(r.image_status=="broken" for r in media_rows)}}
 if not media_rows:
  urls=[p.product_url for p in products if p.product_url and valid_http_url(p.product_url)];verified=await verify_product_urls(urls[:500],concurrency=20);media={"products_checked":len(verified),"url":{"missing":fields["product_url"]["missing"],"valid":sum(verified.values()),"broken":sum(not x for x in verified.values())},"image":{"missing":fields["image_url"]["missing"],"valid":0,"broken":0},"sample_capped":len(urls)>500}
 else:media["persisted"]=True
 base=fields["name"]["coverage_percent"]*.30+fields["price"]["coverage_percent"]*.25+fields["image_url"]["coverage_percent"]*.20+fields["product_url"]["coverage_percent"]*.25;invalid_count=sum(dq.get("invalid_counts",{}).values()) if dq.get("invalid_counts") else sum(len(v) for v in invalid.values() if isinstance(v,list));dup_penalty=min(10,duplicates.get("duplicate_id_count",0)*.6+duplicates.get("duplicate_sku_count",0)*.4);health=max(0,min(100,round(base-min(12,invalid_count*.2)-dup_penalty-min(10,(media.get("url",{}).get("broken",0)+media.get("image",{}).get("broken",0))*.25)-min(5,(latest.skipped if latest else 0)*.25)-min(10,(latest.reconciliation or {}).get("unexplained",0)*.5 if latest and not (latest.reconciliation or {}).get("reconciled",True) else 0))))
 return {"datasource_id":datasource_id,"store_id":store.id,"products":total,"health_score":health,"rating":"Excellent" if health>=90 else "Good" if health>=75 else "Fair" if health>=60 else "Poor","fields":fields,"media_health":media,"duplicates":duplicates,"invalid_data":invalid,"latest_sync":{"id":latest.id,"status":latest.status,"sync_mode":latest.sync_mode,"created":latest.created,"updated":latest.updated,"unchanged":latest.unchanged,"skipped":latest.skipped,"stale":report.get("stale",{}),"price_changes":report.get("price_changes",{}),"stock_changes":report.get("stock_changes",{}),"schema_drift":report.get("schema_drift",{}),"repair_suggestions":report.get("repair_suggestions",[])} if latest else None}
@router.get("/{datasource_id}/issues")
def list_sync_issues(datasource_id:str,field:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);run=db.query(SyncRun).filter(SyncRun.store_id==store.id,SyncRun.datasource_id==datasource_id).order_by(SyncRun.started_at.desc()).first()
 if run is None:raise HTTPException(404,detail="no sync history found")
 dq=((run.quality_report or {}).get("data_quality") or {});samples=dq.get("issue_samples") or {};invalid=dq.get("invalid_data") or {};allowed=set(samples)|set(invalid)|{"duplicates","price_changes","stock_changes","stale","schema_drift","repair_suggestions"}
 if field:
  key=field.strip();items=list(samples.get(key,[]))
  if not items and key in invalid:items=list(invalid.get(key,[]))
  if key=="duplicates":items=list((dq.get("duplicates") or {}).get("candidates",[]))
  if key=="price_changes":items=list((run.quality_report or {}).get("price_changes",{}).get("items",[]))
  if key=="stock_changes":items=list((run.quality_report or {}).get("stock_changes",{}).get("items",[]))
  total=len(items);start=(page-1)*page_size;return {"datasource_id":datasource_id,"run_id":run.id,"field":key,"page":page,"page_size":page_size,"total":total,"items":items[start:start+page_size]}
 issue_fields={}
 for key in allowed:
  vals=list(samples.get(key,[]))
  if not vals and key in invalid:vals=list(invalid.get(key,[]))
  if vals:issue_fields[key]={"count":len(vals),"sample":vals[:page_size]}
 return {"datasource_id":datasource_id,"run_id":run.id,"page":page,"page_size":page_size,"fields":issue_fields}
@router.get("/{datasource_id}/schema-approval")
def get_schema_approval(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);ds=DataSourceService(db).get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 m=ds.mapping or {};return {"datasource_id":datasource_id,"approval":m.get("_schema_approval",{}),"current_mapping":{k:v for k,v in m.items() if not k.startswith("_")},"pending_mapping":m.get("_pending_mapping"),"pending_schema":m.get("_pending_schema")}
@router.post("/{datasource_id}/schema-approval")
def approve_schema(datasource_id:str,payload:SchemaApprovalRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);ds=DataSourceService(db).get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 m=dict(ds.mapping or {});pending=m.get("_pending_mapping")
 if not pending:raise HTTPException(409,detail="no pending schema mapping requires approval")
 if payload.action=="approve":
  for k,v in pending.items():m[k]=v
  m.pop("_pending_mapping",None);m.pop("_pending_schema",None);m["_schema_approval"]={"status":"approved","approved_at":__import__("datetime").datetime.utcnow().isoformat()}
 else:
  candidate_hash=(m.get("_schema_approval") or {}).get("candidate_hash");m.pop("_pending_mapping",None);m.pop("_pending_schema",None);m["_schema_approval"]={"status":"rejected","rejected_at":__import__("datetime").datetime.utcnow().isoformat(),"candidate_hash":candidate_hash}
 ds.mapping=m;db.commit();return {"datasource_id":datasource_id,"action":payload.action,"approval":m["_schema_approval"],"mapping":{k:v for k,v in m.items() if not k.startswith("_")}}
@router.get("/{datasource_id}/sync-runs")
def list_sync_runs(datasource_id:str,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 if DataSourceService(db).get(store.id,datasource_id) is None:raise HTTPException(404,detail="datasource not found")
 q=db.query(SyncRun).filter(SyncRun.store_id==store.id,SyncRun.datasource_id==datasource_id).order_by(SyncRun.started_at.desc());total=q.count();items=q.offset(offset).limit(limit).all();return {"datasource_id":datasource_id,"count":total,"limit":limit,"offset":offset,"items":[{"id":r.id,"status":r.status,"sync_mode":r.sync_mode,"started_at":r.started_at,"finished_at":r.finished_at,"duration_ms":r.duration_ms,"products_seen":r.products_seen,"created":r.created,"updated":r.updated,"unchanged":r.unchanged,"skipped":r.skipped,"health_score":r.health_score,"reconciliation":r.reconciliation,"error":r.error} for r in items]}
@router.get("/{datasource_id}/sync-runs/{run_id}")
def get_sync_run(datasource_id:str,run_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);run=db.query(SyncRun).filter(SyncRun.id==run_id,SyncRun.store_id==store.id,SyncRun.datasource_id==datasource_id).first()
 if run is None:raise HTTPException(404,detail="sync run not found")
 return {"id":run.id,"datasource_id":run.datasource_id,"store_id":run.store_id,"status":run.status,"sync_mode":run.sync_mode,"started_at":run.started_at,"finished_at":run.finished_at,"duration_ms":run.duration_ms,"products_seen":run.products_seen,"created":run.created,"updated":run.updated,"unchanged":run.unchanged,"skipped":run.skipped,"stock_zeroed":run.stock_zeroed,"health_score":run.health_score,"quality_report":run.quality_report,"reconciliation":run.reconciliation,"error":run.error}
@router.patch("/{datasource_id}")
def update_datasource(datasource_id:str,payload:UpdateDataSourceRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 try:ds=DataSourceService(db).update(store.id,datasource_id,**payload.model_dump(exclude_unset=True))
 except LookupError as exc:raise HTTPException(404,detail=str(exc)) from exc
 except(ConnectionError,ValueError) as exc:raise HTTPException(400,detail=str(exc)) from exc
 return public_datasource_dict(ds)
@router.delete("/{datasource_id}")
def delete_datasource(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 if not DataSourceService(db).delete(store.id,datasource_id):raise HTTPException(404,detail="datasource not found")
 return {"status":"deleted","id":datasource_id}
@router.post("/{datasource_id}/discover")
def discover_datasource(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);service=DataSourceService(db);ds=service.get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 if not ds.connection_url:raise HTTPException(400,detail="no connection_url configured")
 if ds.connector_type not in {"postgresql","mysql"}:raise HTTPException(400,detail="discovery supported only for postgresql/mysql")
 plaintext=service.decrypt_connection_url(ds)
 try:result=service.discover(plaintext)
 except Exception as exc:raise HTTPException(400,detail=f"discovery failed: {type(exc).__name__}") from exc
 result["datasource_id"]=ds.id;result["connection_url"]=redact_url(plaintext);return result
@router.post("/{datasource_id}/sync",status_code=202)
async def trigger_sync(datasource_id:str,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC);service=DataSourceService(db);ds=service.get(store.id,datasource_id)
 if ds is None:raise HTTPException(404,detail="datasource not found")
 if not ds.active:raise HTTPException(400,detail="datasource is inactive")
 if ds.connector_type not in SUPPORTED_SYNC_TYPES:raise HTTPException(400,detail="product sync not supported for this connector type")
 if not ds.mapping:raise HTTPException(400,detail="mapping must be configured before sync")
 if ds.connector_type!="rest" and not ds.table_name:raise HTTPException(400,detail="table_name must be configured before sync")
 if ds.connector_type!="rest" and not ds.connection_url:raise HTTPException(400,detail="no connection_url configured")
 if ds.connector_type=="rest" and not ds.api_base_url:raise HTTPException(400,detail="no api_base_url configured")
 queue=SyncQueue(settings.redis_url)
 try:message_id=await queue.enqueue(service.build_sync_job(ds))
 except Exception as exc:raise HTTPException(503,detail="sync queue unavailable") from exc
 finally:await queue.close()
 ds.last_sync_status="queued";ds.last_sync_error=None;db.commit();return {"datasource_id":ds.id,"store_id":store.id,"status":"queued","message":"sync queued for durable background processing","queue_message_id":message_id}
