"""Operator-only sync queue diagnostics and safe DLQ replay."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_auth import get_current_admin
from app.core.config import settings
from app.db.admin_audit import AdminAuditLog
from app.db.database import get_db
from app.sync.dlq import SyncDLQManager

router = APIRouter(prefix="/v1/admin/sync-queue", tags=["platform-admin-sync-queue"])


class DLQReplayRequest(BaseModel):
    message_ids: list[str] = Field(min_length=1, max_length=50)


async def _manager() -> SyncDLQManager:
    from redis.asyncio import from_url

    client = from_url(settings.redis_url, decode_responses=True)
    return SyncDLQManager(client)


@router.get("/dlq")
async def inspect_dlq(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    admin=Depends(get_current_admin),
):
    manager = await _manager()
    try:
        return await manager.inspect(limit=limit, cursor=cursor)
    finally:
        await manager.redis.aclose()


@router.post("/dlq/replay")
async def replay_known_fixed_dlq(
    payload: DLQReplayRequest,
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    manager = await _manager()
    try:
        try:
            result = await manager.replay_known_fixed(payload.message_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        db.add(
            AdminAuditLog(
                admin_id=admin.id,
                action="sync_queue.dlq_replay",
                store_id=None,
                details=json.dumps(result, ensure_ascii=False, sort_keys=True),
            )
        )
        db.commit()
        return result
    finally:
        await manager.redis.aclose()
