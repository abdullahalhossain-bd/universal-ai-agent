"""
Mapping Confirmation API.

Production flow:
  POST /mapping/suggest   → run discovery + confidence decisions
  POST /mapping/confirm   → merchant accepts / overrides fields
  POST /mapping/apply     → persist mapping onto a datasource
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.connectors.mapping_confirmation import (
    MappingConfirmationService,
)
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import DataSource, Store


router = APIRouter(
    prefix="/mapping",
    tags=["Mapping"],
)


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
    # Merchant choices: semantic_field → column
    choices: dict[str, str] = Field(default_factory=dict)


class ApplyMappingRequest(BaseModel):
    store_id: str
    datasource_id: str
    table: str
    # Final semantic_field → column mapping
    mapping: dict[str, str]


@router.post("/suggest")
async def suggest_mapping(
    payload: SuggestMappingRequest,
    store: Store = Depends(get_current_store),
):
    """
    Run field discovery and return auto-accept / ask / manual buckets.
    """
    _ = store
    service = MappingConfirmationService()
    result = service.confirm(
        table=payload.table,
        columns=payload.columns,
        sample_data=payload.sample_data,
        merchant_overrides=payload.overrides,
    )
    return result.to_dict()


@router.post("/confirm")
async def confirm_mapping(
    payload: ConfirmMappingRequest,
    store: Store = Depends(get_current_store),
):
    """
    Merchant confirms or overrides suggested columns.
    Returns updated decision set and whether sync can proceed.
    """
    _ = store
    service = MappingConfirmationService()

    baseline = service.confirm(
        table=payload.table,
        columns=payload.columns,
        sample_data=payload.sample_data,
    )

    if payload.choices:
        result = service.apply_merchant_choices(
            baseline,
            payload.choices,
        )
    else:
        result = baseline

    body = result.to_dict()
    body["sync_mapping"] = service.to_sync_mapping(result)
    return body


@router.post("/apply")
async def apply_mapping(
    payload: ApplyMappingRequest,
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    """
    Persist a confirmed mapping onto an existing datasource.
    Requires id + name at minimum.

    Tenant isolation: the datasource must belong to the store
    identified by the caller's API key. payload.store_id is
    validated against that authenticated store rather than
    trusted on its own — otherwise any caller could target a
    different tenant's datasource by guessing/supplying its id.
    """
    if "id" not in payload.mapping or "name" not in payload.mapping:
        raise HTTPException(
            status_code=400,
            detail="mapping must include at least 'id' and 'name'",
        )

    if payload.store_id != store.id:
        raise HTTPException(
            status_code=403,
            detail="store_id does not match the authenticated store",
        )

    ds = (
        db.query(DataSource)
        .filter(
            DataSource.store_id == store.id,
            DataSource.id == payload.datasource_id,
        )
        .first()
    )
    if ds is None:
        raise HTTPException(status_code=404, detail="datasource not found")

    ds.mapping = dict(payload.mapping)
    if payload.table:
        ds.table_name = payload.table

    db.commit()
    db.refresh(ds)

    return {
        "status": "applied",
        "datasource_id": ds.id,
        "table": ds.table_name,
        "mapping": ds.mapping,
    }
