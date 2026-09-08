"""Merchant datasource onboarding API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.tenant import get_current_store
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.config import settings
from app.datasources.redaction import public_datasource_dict, redact_url
from app.datasources.service import DataSourceService, SUPPORTED_SYNC_TYPES
from app.db.database import get_db
from app.db.models import Store
from app.sync.queue import SyncQueue
router=APIRouter(prefix="/v1/datasources",tags=["datasources"])
class CreateDataSourceRequest(BaseModel):
 name:str="default"; connector_type:str; connection_url:str|None=None; api_base_url:str|None=None; table_name:str|None=None; mapping:dict[str,Any]|None=None; active:bool=True; full_sync:bool=True; skip_connection_test:bool=False
class UpdateDataSourceRequest(BaseModel):
 name:str|None=None; connection_url:str|None=None; api_base_url:str|None=None; table_name:str|None=None; mapping:dict[str,Any]|None=None; active:bool|None=None; full_sync:bool|None=None
class TestConnectionRequest(BaseModel): connector_type:str; connection_url:str|None=None; api_base_url:str|None=None
class DiscoverRequest(BaseModel): connection_url:str=Field(min_length=1); connector_type:str="postgresql"
@router.post("")
async def create_datasource(payload:CreateDataSourceRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 try: ds=DataSourceService(db).create(store.id,name=payload.name,connector_type=payload.connector_type,connection_url=payload.connection_url,api_base_url=payload.api_base_url,table_name=payload.table_name,mapping=payload.mapping,active=payload.active,full_sync=payload.full_sync,validate_connection=not payload.skip_connection_test)
 except (ValueError,ConnectionError) as exc:raise HTTPException(400,detail=str(exc)) from exc
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
@router.patch("/{datasource_id}")
def update_datasource(datasource_id:str,payload:UpdateDataSourceRequest,db:Session=Depends(get_db),store:Store=Depends(get_current_store)):
 require_feature(store,FEATURE_DATABASE_SYNC)
 try:ds=DataSourceService(db).update(store.id,datasource_id,**payload.model_dump(exclude_unset=True))
 except LookupError as exc:raise HTTPException(404,detail=str(exc)) from exc
 except (ConnectionError,ValueError) as exc:raise HTTPException(400,detail=str(exc)) from exc
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
 try:
  message_id=await queue.enqueue(service.build_sync_job(ds))
  if message_id is None:
   return {"datasource_id":ds.id,"store_id":store.id,"status":"already_queued","message":"a sync for this datasource is already queued or running"}
 except Exception as exc:raise HTTPException(503,detail="sync queue unavailable") from exc
 finally:await queue.close()
 ds.last_sync_status="queued";ds.last_sync_error=None;db.commit()
 return {"datasource_id":ds.id,"store_id":store.id,"status":"queued","message":"sync queued for durable background processing","queue_message_id":message_id}
