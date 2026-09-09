"""Sync job processor with datasource-scoped incremental cursors."""
from __future__ import annotations
import inspect
import logging
from datetime import datetime
from app.connectors.config import ConnectorConfig
from app.connectors.credential_store import get_credential_store
from app.connectors.factory import ConnectorFactory
from app.db.database import SessionLocal
from app.sync.normalize import discover_mapping
from app.sync.result import SyncResult
from app.sync.service import ProductSyncService
logger=logging.getLogger("app.sync.processor")
def _resolve_job(job,db):
    store_id=job.get("store_id") or job.get("tenant_id"); datasource_id=job.get("datasource_id")
    if not datasource_id:return {"store_id":store_id,"datasource_id":None,"connector_type":job.get("connector_type"),"connection_url":job.get("connection_url"),"api_base_url":job.get("api_base_url"),"table_name":job.get("table_name"),"mapping":job.get("mapping") or {},"full_sync":bool(job.get("full_sync",True)),"job_type":job.get("job_type","product_sync")}
    from app.db.models import DataSource
    ds=db.query(DataSource).filter(DataSource.id==datasource_id,DataSource.store_id==store_id).first()
    if ds is None:raise LookupError(f"datasource {datasource_id} not found for store {store_id}")
    if not ds.active:raise PermissionError(f"datasource {datasource_id} is inactive")
    decrypted=get_credential_store().decrypt(ds.connection_url) if ds.connection_url else None
    return {"store_id":store_id,"datasource_id":ds.id,"connector_type":ds.connector_type,"connection_url":decrypted or job.get("connection_url"),"api_base_url":ds.api_base_url,"table_name":ds.table_name or job.get("table_name"),"mapping":ds.mapping or job.get("mapping") or {},"full_sync":bool(ds.full_sync if "full_sync" not in job else job.get("full_sync",True)),"job_type":job.get("job_type","product_sync")}
def _mapping_column(mapping,field):
    entry=mapping.get(field); return entry.get("column") if isinstance(entry,dict) else (entry or None)
def _persist_watermark(db,datasource_id,mapping,connector,table_name,*,upper_bound=None):
    if not datasource_id or not hasattr(connector,"get_sync_watermark"):return
    ts=_mapping_column(mapping,"updated_at") or _mapping_column(mapping,"created_at"); ident=_mapping_column(mapping,"id")
    if not ts and not ident:return
    watermark=connector.get_sync_watermark(table_name,ts,ident,upper_bound=upper_bound)
    if not watermark:return
    from app.db.models import DataSource
    ds=db.query(DataSource).filter(DataSource.id==datasource_id).first()
    if ds is None:return
    state=dict((ds.mapping or {}).get("_sync_state") or {}); state["initialized"]=True
    if watermark.get("watermark_at") is not None:
        value=watermark["watermark_at"]; state["watermark_at"]=value.isoformat() if isinstance(value,datetime) else str(value)
    if watermark.get("watermark_id") is not None:state["watermark_id"]=str(watermark["watermark_id"])
    state["strategy"]="updated_at+id" if _mapping_column(mapping,"updated_at") else ("created_at+id" if _mapping_column(mapping,"created_at") else "id")
    new_mapping=dict(ds.mapping or {}); new_mapping["_sync_state"]=state; ds.mapping=new_mapping; db.commit()
async def _auto_discover_mapping(connector,table_name,mapping):
    """Discover live source columns and fill only missing semantic mappings."""
    effective=dict(mapping or {})
    discover=getattr(connector,"discover",None)
    if discover is None:return effective
    try:
        schema=discover()
        if inspect.isawaitable(schema):schema=await schema
    except Exception:
        # A merchant REST API may not expose /schema. Keep an already usable
        # explicit mapping working; required-field validation will still guard
        # incomplete mappings downstream.
        if _mapping_column(effective,"id") and _mapping_column(effective,"name"):
            return effective
        raise
    tables=getattr(schema,"tables",None)
    if tables is None and isinstance(schema,dict):tables=schema.get("tables",[])
    target=None
    for table in tables or []:
        name=getattr(table,"name",None) if not isinstance(table,dict) else table.get("name")
        if str(name)==str(table_name):target=table;break
    if target is None:return effective
    columns=getattr(target,"columns",None) if not isinstance(target,dict) else target.get("columns",[])
    names=[]
    for column in columns or []:
        name=getattr(column,"name",None) if not isinstance(column,dict) else column.get("name")
        if name:names.append(str(name))
    if not names:return effective
    sample={name:None for name in names}
    inferred=discover_mapping(sample,effective)
    for field,column in inferred.items():
        if field.startswith("_"):continue
        if column and not effective.get(field):effective[field]=column
    effective["_schema_discovery"]={"table":str(table_name),"columns":names}
    return effective
async def process_sync(job):
    store_id=job.get("store_id") or job.get("tenant_id")
    if not store_id:result=SyncResult(store_id="");result.errors.append("job missing store_id");return result
    db=SessionLocal()
    try:
        try:resolved=_resolve_job(job,db)
        except (LookupError,PermissionError) as exc:result=SyncResult(store_id=store_id);result.errors.append(str(exc));return result
        connector_type=resolved["connector_type"];connection_url=resolved["connection_url"];table_name=resolved["table_name"];mapping=resolved["mapping"] or {};full_sync=resolved["full_sync"];job_type=resolved["job_type"];datasource_id=resolved.get("datasource_id")
        if not connector_type:result=SyncResult(store_id=store_id);result.errors.append("job missing connector_type");return result
        if connector_type=="rest":
            if not resolved.get("api_base_url") and not connection_url:result=SyncResult(store_id=store_id);result.errors.append("job missing api_base_url");return result
            config=ConnectorConfig(connector_type="rest",api_base_url=resolved.get("api_base_url") or connection_url,options=(mapping.get("_rest_options") or {}));connector=ConnectorFactory.create(config)
        else:
            if not connection_url:result=SyncResult(store_id=store_id);result.errors.append("job missing connection_url");return result
            connector=ConnectorFactory.create(connector_type,connection_url)
        if not table_name:result=SyncResult(store_id=store_id);result.errors.append("job missing table_name");return result
        mapping=await _auto_discover_mapping(connector,table_name,mapping)
        if datasource_id and mapping != resolved["mapping"]:
            from app.db.models import DataSource
            ds=db.query(DataSource).filter(DataSource.id==datasource_id,DataSource.store_id==store_id).first()
            if ds is not None:
                ds.mapping=mapping;db.commit()
        service=ProductSyncService(db)
        if job_type=="stock_refresh":
            columns=[(e.get("column") if isinstance(e,dict) else e) for f,e in mapping.items() if f not in {"_sync_state","_schema_discovery","_rest_options"} and (e.get("column") if isinstance(e,dict) else e)]; rows=[];offset=0
            while True:
                page=connector.fetch_product_rows(table_name,columns,limit=200,offset=offset)
                if not page:break
                rows.extend(page)
                if len(page)<200:break
                offset+=200
            result=service.refresh_stock(store_id,rows,mapping)
        else:
            state=mapping.get("_sync_state") or {}; sync_upper_bound=datetime.utcnow() if state.get("initialized") and (_mapping_column(mapping,"updated_at") or _mapping_column(mapping,"created_at")) else None
            result=service.sync_from_connector(store_id,connector,table_name,mapping,full_sync=full_sync,sync_state=state,sync_upper_bound=sync_upper_bound,source_datasource_id=datasource_id)
            if not result.errors:_persist_watermark(db,datasource_id,mapping,connector,table_name,upper_bound=sync_upper_bound)
        if datasource_id:
            from app.datasources.service import DataSourceService
            DataSourceService(db).record_sync_result(store_id,datasource_id,status="success" if not result.errors else "error",error="; ".join(result.errors) if result.errors else None)
        if result.created or result.updated:
            from app.search.store_vocabulary import invalidate_store_vocabulary
            await invalidate_store_vocabulary(store_id)
        return result
    except Exception as exc:
        logger.exception("process_sync failed store=%s",store_id);result=SyncResult(store_id=store_id);result.errors.append(str(exc));return result
    finally:db.close()