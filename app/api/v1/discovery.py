"""
Universal Database Discovery API.

Flow:
  Merchant DB URL
    → Schema Scan
    → Sample Values
    → Field + Table Detection
    → Confidence decisions
    → Mapping suggestions (for confirmation UI)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.tenant import get_current_store
from app.core.network_guard import assert_safe_connection_host
from app.db.models import Store
from app.discovery.service import DiscoveryService
from app.connectors.mapping_confirmation import (
    MappingConfirmationService,
)


router = APIRouter(
    prefix="/discovery",
    tags=["Discovery"],
)


class ScanRequest(BaseModel):
    connection_url: str = Field(
        ...,
        description="Merchant database SQLAlchemy URL",
    )
    table: str | None = Field(
        None,
        description="Optional: focus on a single table for mapping",
    )


@router.post("/scan")
async def scan_database(
    payload: ScanRequest,
    store: Store = Depends(get_current_store),
):
    """
    Full schema discovery against a merchant database.

    Requires an authenticated store API key — this endpoint
    accepts an arbitrary connection_url and must never be
    reachable without tenant auth.
    """
    _ = store
    if not payload.connection_url:
        raise HTTPException(
            status_code=400,
            detail="connection_url is required",
        )

    # SSRF guard: resolve the actual host and reject anything that
    # is, or resolves to, a private/loopback/link-local/metadata
    # address. A substring blocklist alone is bypassable (decimal/
    # hex IP encodings, DNS rebinding), so this does a real lookup.
    try:
        assert_safe_connection_host(payload.connection_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"connection to private/internal hosts is not allowed: {exc}",
        ) from exc

    try:
        service = DiscoveryService(payload.connection_url)
        result = service.discover()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"discovery failed: {type(exc).__name__}: {exc}",
        ) from exc

    body = result.model_dump(by_alias=True)

    # If a specific table was requested, attach mapping confirmation
    if payload.table:
        table_info = next(
            (t for t in result.db_schema.tables if t.name == payload.table),
            None,
        )
        if table_info is None:
            raise HTTPException(
                status_code=404,
                detail=f"table '{payload.table}' not found in schema",
            )

        columns = [
            {"name": c.name, "type": c.data_type}
            for c in table_info.columns
        ]
        confirm = MappingConfirmationService().confirm(
            table=payload.table,
            columns=columns,
        )
        body["mapping_confirmation"] = confirm.to_dict()

    return body
