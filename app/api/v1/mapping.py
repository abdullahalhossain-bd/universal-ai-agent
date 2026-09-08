"""Mapping confirmation API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.connectors.mapping_confirmation import MappingConfirmationService
from app.core.features import FEATURE_DATABASE_SYNC, require_feature
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import DataSource, Store
from app.products.sql_identifier import validate_identifier

router = APIRouter(prefix="/mapping", tags=["Mapping"])
class ColumnPayload(BaseModel):
    name: str
    type: str | None = None
class SuggestMappingRequest(BaseModel):
    store_id: str
    table: str
    columns: list[ColumnPayload] | list[str]
    sample_data: dict[str, list[Any]] | None = None
    overrides: dict[str, str] | None = None
class ConfirmMappingRequest(BaseModel):
    store_id: str
    table: str
    columns: list[ColumnPayload] | list[str]
    sample_data: dict[str, list[Any]] | None = None
    choices: dict[str, str] = Field(default_factory=dict)
class ApplyMappingRequest(BaseModel):
    store_id: str
    datasource_id: str
    table: str
    mapping: dict[str, str]

@router.post("/suggest")
async def suggest_mapping(payload: SuggestMappingRequest, store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    result=MappingConfirmationService().confirm(table=payload.table, columns=payload.columns, sample_data=payload.sample_data, merchant_overrides=payload.overrides)
    return result.to_dict()

@router.post("/confirm")
async def confirm_mapping(payload: ConfirmMappingRequest, store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    service=MappingConfirmationService(); baseline=service.confirm(table=payload.table, columns=payload.columns, sample_data=payload.sample_data)
    result=service.apply_merchant_choices(baseline,payload.choices) if payload.choices else baseline
    body=result.to_dict(); body["sync_mapping"]=service.to_sync_mapping(result); return body

@router.post("/apply")
async def apply_mapping(payload: ApplyMappingRequest, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    require_feature(store, FEATURE_DATABASE_SYNC)
    if payload.store_id != store.id: raise HTTPException(status_code=403, detail="store_id does not match the authenticated store")
    if not payload.table: raise HTTPException(status_code=400, detail="table is required")
    try: validate_identifier(payload.table)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    for required in ("id","name"):
        if not payload.mapping.get(required): raise HTTPException(status_code=400, detail=f"mapping must include at least '{required}'")
    seen={}
    for field,col in payload.mapping.items():
        if field == "_sync_state" or not col: continue
        try: validate_identifier(str(col))
        except ValueError as exc: raise HTTPException(status_code=400, detail=f"invalid mapping column for {field}: {exc}") from exc
        if col in seen and seen[col] != field: raise HTTPException(status_code=400, detail=f"column {col!r} is mapped to both {seen[col]!r} and {field!r}")
        seen[col]=field
    ds=db.query(DataSource).filter(DataSource.store_id==store.id, DataSource.id==payload.datasource_id).first()
    if ds is None: raise HTTPException(status_code=404, detail="datasource not found")
    if ds.connector_type in {"postgresql","mysql","postgres"}:
        if not ds.connection_url: raise HTTPException(status_code=400, detail="datasource has no connection URL")
        try: DataSourceService(db).validate_mapping(DataSourceService.decrypt_connection_url(ds), payload.table, payload.mapping)
        except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    previous=dict(ds.mapping or {}); new_mapping=dict(payload.mapping)
    if previous.get("_sync_state"): new_mapping["_sync_state"]=previous["_sync_state"]
    ds.mapping=new_mapping; ds.table_name=payload.table; db.commit(); db.refresh(ds)
    return {"status":"applied","datasource_id":ds.id,"table":ds.table_name,"mapping":ds.mapping}

from app.datasources.service import DataSourceService
